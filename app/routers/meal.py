"""학식 관련 API 파일입니다.

학식 관련 API가 작성되어 있습니다.
학식 보기, 등록, 삭제 등의 기능을 담당합니다.
"""

import asyncio
from copy import deepcopy
from typing import Annotated, List, Literal
from datetime import datetime, timedelta

from fastapi import Depends, APIRouter
from fastapi.responses import JSONResponse

from httpx import HTTPStatusError
from kakao_chatbot import Payload
from kakao_chatbot.context import Context
from kakao_chatbot.response import KakaoResponse, QuickReply, ActionEnum
from kakao_chatbot.response.components import SimpleTextComponent, ItemCardComponent
from kakao_chatbot.response.components import ImageTitle

from app.config import Config, logger
from app.config.blocks import BlockID
from app.schemas.meals import (
    MealCard,
    MealResponse,
    MealType,
    RestaurantResponse,
)
from app.models.users import User
from app.services.meal_service import (
    fetch_latest_meals,
    fetch_restaurant_by_name,
    post_meal,
)
from app.utils.auth_client import get_xuser_client_by_payload
from app.utils.user import get_current_user, sync_required
from app.utils.http import XUserIDClient
from app.utils import create_openapi_extra
from app.utils.kakao import parse_payload
from app.utils.meal import (
    establishment_type_to_string,
    extract_menu,
    make_meal_cards,
    meal_error_response_maker,
    meal_response_maker,
    save_menu,
    select_restaurant,
    split_string,
    time_range_to_string,
)

meal_router = APIRouter(prefix="/meal")


@meal_router.post(
    "/view",
    openapi_extra=create_openapi_extra(
        detail_params={
            "Cafeteria": {
                "origin": "미가",
                "value": "미가식당",
            },
        },
        utterance="학식 미가",
    ),
)
async def meal_view(
    payload: Annotated[Payload, Depends(parse_payload)],
    client: Annotated[XUserIDClient, Depends(get_xuser_client_by_payload)],
) -> JSONResponse:
    """식단 정보를 Carousel TextCard 형태로 반환합니다.

    등록된 식당 정보를 불러와 어제 7시 이후 등록된 식당 정보를 먼저 배치합니다.
    그 후 어제 7시 이전 등록된 식당 정보를 배치합니다.
    이를 통해 어제 7시 이후 등록된 식당 정보가 먼저 보이도록 합니다.
    이를 토대로 점심과 저녁 메뉴를 담은 Carousel을 생성합니다.

    ## 카카오 챗봇 연결 정보
    ---
    - 동작방식: 발화
        - "학식"
        - "학식 <식당>"
        - "메뉴 <식당>"
        - 등

    - OpenBuilder:
        - 블럭: "학식 보기"
        - 스킬: "학식 보기"

    - Params:
        - detail_params:
            - Cafeteria(식당): 식당 이름(Optional)
    ---

    Returns:
        str: 식단 정보를 반환합니다.
    """
    logger.info("식단 정보 조회 요청 수신: kakao_id=%s", payload.user_request.user.id)

    # payload에서 Cafeteria 값 추출
    cafeteria = payload.action.detail_params.get("Cafeteria")  # 학식 이름
    target_cafeteria = getattr(cafeteria, "value", None)

    # 식단 정보를 가져옵니다.
    meal_list = await fetch_latest_meals(client)

    # cafeteria 값이 있을 경우 해당 식당 정보로 필터링
    if target_cafeteria:
        logger.debug("식단 정보 필터링: target_cafeteria=%s", target_cafeteria)
        meals = list(filter(lambda x: x.restaurant_name == target_cafeteria, meal_list))
    else:
        meals = meal_list

    # 어제 7시를 기준으로 식당 정보를 필터링
    logger.debug("식당 정보 정렬 시작")
    standard_time = datetime.now(tz=Config.TZ) - timedelta(days=1)
    standard_time = standard_time.replace(hour=19, minute=0, second=0, microsecond=0)
    af_standard: list[MealResponse] = []
    bf_standard: list[MealResponse] = []
    for meal in meals:
        if meal.updated_at < standard_time:
            logger.debug(
                "식당 정보 정렬: %s | 어제 7시 이전 등록", meal.restaurant_name
            )
            bf_standard.append(meal)
        else:
            logger.debug(
                "식당 정보 정렬: %s | 어제 7시 이후 등록", meal.restaurant_name
            )
            af_standard.append(meal)

    bf_standard.sort(key=lambda x: x.updated_at)
    af_standard.sort(key=lambda x: x.updated_at)

    # 어제 7시 이후 등록된 식당 정보를 먼저 배치
    restaurants = af_standard + bf_standard

    lunch = []
    dinner = []
    for meal in restaurants:
        if meal.meal_type == MealType.lunch:
            lunch.append(meal)
        elif meal.meal_type == MealType.dinner:
            dinner.append(meal)
        else:
            logger.warning(
                "식단 정보 오류: kakao_id=%s, meal_type=%s",
                payload.user_request.user.id,
                meal.meal_type,
            )

    # 점심과 저녁 메뉴를 담은 Carousel 생성
    lunch_carousel, dinner_carousel = make_meal_cards(lunch, dinner)

    response = KakaoResponse()

    # 점심과 저녁 메뉴 Carousel을 SkillList에 추가
    # 비어있는 Carousel을 추가하지 않음
    if not lunch_carousel.is_empty:
        response.add_component(lunch_carousel)
    if not dinner_carousel.is_empty:
        response.add_component(dinner_carousel)
    if not response.component_list:
        logger.debug("식단 정보가 없습니다: kakao_id=%s", payload.user_request.user.id)
        response.add_component(SimpleTextComponent("식단 정보가 없습니다."))

    # 퀵리플라이 추가
    # 현재 선택된 식단을 제외한 다른 식당을 퀵리플라이로 추가
    if target_cafeteria:
        response.add_quick_reply(
            label="모두 보기",
            action="message",
            message_text="학식",
        )

    inserted_restaurant = set()
    for meal in meal_list:
        if (
            meal.restaurant_name != target_cafeteria
            and meal.restaurant_name not in inserted_restaurant
        ):
            response.add_quick_reply(
                label=meal.restaurant_name,
                action="message",
                message_text=f"학식 {meal.restaurant_name}",
            )
            inserted_restaurant.add(meal.restaurant_name)

    logger.info("식단 정보 조회 완료: kakao_id=%s", payload.user_request.user.id)
    return JSONResponse(response.get_dict())


@meal_router.post(
    "/restaurant",
    openapi_extra=create_openapi_extra(
        client_extra={
            "restaurant_name": "미가식당",
        }
    ),
)
async def meal_restaurant(
    payload: Annotated[Payload, Depends(parse_payload)],
    user: Annotated[User, Depends(get_current_user)],
    client: Annotated[XUserIDClient, Depends(get_xuser_client_by_payload)],
) -> JSONResponse:
    """식당 정보를 반환하는 API입니다.

    식당의 운영시간, 위치, 가격 등의 정보를 반환합니다.

    ## 카카오 챗봇 연결 정보
    ---
    - 동작방식: 버튼 연결

    - OpenBuilder:
        블럭: "식당 정보"
        스킬: "식당 정보"

    - Params:
        - client_extra:
            - restaurant_name(str): 식당 이름
    ---

    Returns:
        str: 식당 정보를 반환합니다.
    """
    logger.info("식당 정보 조회 요청 수신: kakao_id=%s", payload.user_id)
    restaurant_name: str = payload.action.client_extra["restaurant_name"]

    # 식당 정보를 가져옵니다.
    result = await fetch_restaurant_by_name(restaurant_name, client)
    if not result:
        logger.error(
            "식당 정보 조회 실패: kakao_id=%s, restaurant_name=%s",
            payload.user_id,
            restaurant_name,
        )
        return JSONResponse(
            KakaoResponse()
            .add_component(SimpleTextComponent("식당 정보를 찾을 수 없습니다."))
            .get_dict()
        )
    restaurant: RestaurantResponse = result

    item_card = ItemCardComponent([])
    item_card.image_title = ImageTitle(title=restaurant.name, description="식당 정보")
    if restaurant.lunch_time:
        item_card.add_item(
            title="점심 시간", description=time_range_to_string(restaurant.lunch_time)
        )
    if restaurant.dinner_time:
        item_card.add_item(
            title="저녁 시간", description=time_range_to_string(restaurant.dinner_time)
        )
    item_card.add_item(
        title="분류",
        description=establishment_type_to_string(restaurant.establishment_type),
    )
    # item_card.add_item(title="가격", description=f"{restaurant.price_per_person}원")  # TODO: 가격 정보 추가
    item_card.add_button(
        label="메뉴 보기", action="message", message_text=f"학식 {restaurant_name}"
    )
    map_links = getattr(restaurant.location, "map_links", {})
    url = map_links.get("kakao") or map_links.get("naver") if map_links else None
    if url:
        item_card.add_button(
            label="식당 위치 지도 보기", action="webLink", web_link_url=url
        )
    response = KakaoResponse().add_component(item_card)

    logger.info(
        "식당 정보 조회 완료: kakao_id=%s, restaurant_name=%s",
        payload.user_id,
        restaurant_name,
    )

    return JSONResponse(response.get_dict())


@meal_router.post(
    "/register/delete/{meal_type}",
    openapi_extra=create_openapi_extra(
        client_extra={
            "restaurant_name": "산돌식당",
        },
    ),
)
@sync_required()
async def meal_delete(
    meal_type: str,
    payload: Annotated[Payload, Depends(parse_payload)],
    user: Annotated[User, Depends(get_current_user)],
    restaurant: Annotated[
        RestaurantResponse,
        Depends(select_restaurant),
    ],
) -> JSONResponse:
    """삭제할 메뉴를 선택하는 API입니다.

    meal_type에 해당하는 식사 종류의 메뉴를 삭제할 수 있도록
    각 메뉴를 퀵리플라이로 반환합니다.
    퀵리플라이를 통해 삭제할 메뉴를 선택하면 meal_menu_delete API로 이동합니다.
    삭제할 메뉴가 없을 경우 "삭제할 메뉴가 없습니다."를 반환합니다.

    Args:
        meal_type (str): 중식 또는 석식을 나타내는 문자열입니다.
            lunch, dinner 2가지 중 하나의 문자열이어야 합니다.
        payload (Payload): 카카오 챗봇에서 전달된 Payload 객체입니다.
        user (User): 현재 사용자 객체입니다.
        restaurant (RestaurantResponse): 등록된 식당 정보입니다.

    ## 카카오 챗봇 연결 정보
    ---
    - 동작 방식: 버튼 연결

    - OpenBuilder:
        - 블럭:
            - "메뉴 삭제 - 중식"
            - "메뉴 삭제 - 석식"
        - 스킬:
            - "중식 삭제"
            - "석식 삭제"
    ---

    Returns:
        str: 삭제할 수 있는 메뉴 리스트를 반환합니다.
    """
    logger.info(
        "메뉴 삭제 요청 수신: kakao_id=%s, meal_type=%s", payload.user_id, meal_type
    )

    # meal_type에 해당하는 메뉴 리스트를 불러와 퀵리플라이로 반환
    memu_list = extract_menu(payload.contexts, f"{meal_type}_menu", restaurant.name)
    if not memu_list:
        logger.warning(
            "삭제할 메뉴가 없음: kakao_id=%s, meal_type=%s, contexts=%s",
            payload.user_id,
            meal_type,
            [ctx.name for ctx in payload.contexts],
        )
        return JSONResponse(
            KakaoResponse()
            .add_component(SimpleTextComponent("삭제할 메뉴가 없습니다."))
            .get_dict()
        )
    response = KakaoResponse()
    simple_text = SimpleTextComponent("삭제할 메뉴를 선택해주세요.")
    response = response.add_component(simple_text)
    logger.debug(
        "삭제 가능한 메뉴 리스트 생성: kakao_id=%s, meal_type=%s, menu_list=%s",
        payload.user_id,
        meal_type,
        memu_list,
    )
    for menu in memu_list:
        quick_reply = QuickReply(
            label=menu,
            action=ActionEnum.BLOCK,
            block_id=BlockID.DELETE_MENU,
            extra={"meal_type": meal_type, "menu": menu},
        )
        response += quick_reply
    logger.info(
        "메뉴 삭제 리스트 반환 완료: kakao_id=%s, meal_type=%s",
        payload.user_id,
        meal_type,
    )
    return JSONResponse(response.get_dict())


@meal_router.post(
    "/register/delete_all",
    openapi_extra=create_openapi_extra(
        utterance="식단 전체 삭제",
        client_extra={
            "restaurant_name": "산돌식당",
        },
    ),
)
@sync_required()
async def meal_delete_all(
    payload: Annotated[Payload, Depends(parse_payload)],
    user: Annotated[User, Depends(get_current_user)],
    restaurant: Annotated[
        RestaurantResponse,
        Depends(select_restaurant),
    ],
) -> JSONResponse:
    """모든 메뉴를 삭제하는 API입니다.

    모든 메뉴를 삭제하고 삭제된 결과를 응답으로 반환합니다.

    ## 카카오 챗봇 연결 정보
    ---
    - 동작방식: 버튼 연결

    - OpenBuilder:
        - 블럭: "식단 삭제"
        - 스킬: "식단 삭제"
    ---

    Returns:
        str: 모든 메뉴가 삭제되었음을 반환합니다.
    """
    logger.info("모든 메뉴 삭제 요청 수신: user_id=%s", payload.user_id)

    logger.debug("모든 메뉴 삭제: user_id=%s", payload.user_id)
    contexts: List[Context] = deepcopy(payload.contexts)
    contexts = save_menu(
        contexts,
        "lunch_menu",
        restaurant.name,
        [],
        lifspan=0,
        ttl=0,
    )
    contexts = save_menu(
        contexts,
        "dinner_menu",
        restaurant.name,
        [],
        lifspan=0,
        ttl=0,
    )
    lunch, dinner = make_meal_cards([], [])
    response = meal_response_maker(lunch, dinner, is_temp=False)
    response.add_component(SimpleTextComponent("모든 메뉴가 삭제되었습니다."))
    response.contexts = contexts
    logger.info("모든 메뉴 삭제 완료: user_id=%s", payload.user_id)
    return JSONResponse(response.get_dict())


@meal_router.post(
    "/register/delete_menu",
    openapi_extra=create_openapi_extra(
        client_extra={
            "meal_type": "lunch",
            "menu": "김치찌개",
            "restaurant_name": "산돌식당",
        },
    ),
)
@sync_required()
async def meal_menu_delete(
    payload: Annotated[Payload, Depends(parse_payload)],
    user: Annotated[User, Depends(get_current_user)],
    restaurant: Annotated[
        RestaurantResponse,
        Depends(select_restaurant),
    ],
) -> JSONResponse:
    """선택한 메뉴를 삭제하는 API입니다.

    meal_delete API에서 선택한 메뉴를 삭제합니다.
    삭제된 결과를 응답으로 반환합니다.

    ## 카카오 챗봇 연결 정보
    ---
    - 동작방식: 버튼 연결

    - OpenBuilder:
        - 블럭: "메뉴 삭제"
        - 스킬: "메뉴 삭제"

    - Params:
        - client_extra:
            - meal_type(str): 삭제할 식사 종류
            - menu(str): 삭제할 메뉴
    ---

    Returns:
        str: 메뉴가 삭제된 결과를 반환합니다.
    """
    logger.info("메뉴 삭제 요청 수신: user_id=%s", payload.user_id)

    meal_type = payload.action.client_extra.get("meal_type", "")
    menu = payload.action.client_extra.get("menu", "")
    if not meal_type or not menu:
        logger.error(
            "메뉴 삭제 실패: user_id=%s, meal_type=None, menu=None",
            payload.user_id,
        )
        return JSONResponse(
            meal_error_response_maker("삭제할 메뉴를 입력해주세요.").get_dict()
        )

    contexts: List[Context] = deepcopy(payload.contexts)
    menu_list = extract_menu(contexts, f"{meal_type}_menu", restaurant.name)
    logger.debug(
        "메뉴 삭제 시도: user_id=%s, meal_type=%s, menu=%s, menu_list=%s",
        payload.user_id,
        meal_type,
        menu,
        menu_list,
    )
    if menu not in menu_list:
        logger.error(
            "메뉴 삭제 실패(등록되지 않음): user_id=%s, meal_type=%s, menu=%s, menu_list=%s",
            payload.user_id,
            meal_type,
            menu,
            menu_list,
        )
        return JSONResponse(
            meal_error_response_maker("등록되지 않은 메뉴입니다.").get_dict()
        )

    menu_list.remove(menu)
    contexts = save_menu(
        contexts,
        f"{meal_type}_menu",
        restaurant.name,
        menu_list,
    )
    logger.debug(
        "메뉴 삭제 완료: user_id=%s, meal_type=%s, menu=%s",
        payload.user_id,
        meal_type,
        menu_list,
    )

    lunch_menu = extract_menu(contexts, "lunch_menu", restaurant.name)
    dinner_menu = extract_menu(contexts, "dinner_menu", restaurant.name)

    lunch_card = MealCard(
        menu=lunch_menu,
        meal_type=MealType.lunch,
        restaurant_name=restaurant.name,
    )
    dinner_card = MealCard(
        menu=dinner_menu,
        meal_type=MealType.dinner,
        restaurant_name=restaurant.name,
    )
    lunch, dinner = make_meal_cards(lunch_card, dinner_card)

    response = meal_response_maker(lunch, dinner)
    response.contexts = contexts

    logger.info(
        "메뉴 삭제 완료: user_id=%s, meal_type=%s, menu=%s",
        payload.user_id,
        meal_type,
        menu,
    )
    return JSONResponse(response.get_dict())


@meal_router.post(
    "/register/{meal_type}",
    openapi_extra=create_openapi_extra(
        detail_params={
            "menu": {
                "origin": "김치찌개",
                "value": "김치찌개",
            },
        },
        client_extra={
            "restaurant_name": "산돌식당",
        },
    ),
)
@sync_required()
async def meal_register(
    meal_type: Literal["lunch", "dinner"],
    payload: Annotated[Payload, Depends(parse_payload)],
    user: Annotated[User, Depends(get_current_user)],
    restaurant: Annotated[
        RestaurantResponse,
        Depends(select_restaurant),
    ],
) -> JSONResponse:
    """식단 정보를 등록합니다.

    중식 등록 및 석식 등록 스킬을 처리합니다.
    중식 및 석식 등록 발화시 호출되는 API입니다.
    restaurant_name을 통해 사용자가 선택한 식당을 가져옵니다.
    만약, restaurant_name이 없다면, 사용자가 등록한 식당을 가져옵니다.
    사용자가 등록한 식당이 여러개일 경우, 사용자가 선택한 식당을 가져옵니다.

    Args:
        meal_type (Literal): 중식 또는 석식을 나타내는 문자열입니다.
            lunch, dinner 2가지 중 하나의 문자열이어야 합니다.
        payload (Payload): 카카오 챗봇에서 전달된 Payload 객체입니다.
        user (User): 현재 사용자 객체입니다.
        restaurant (RestaurantResponse): 등록된 식당 정보입니다.

    Returns:
        JSONResponse: 등록된 식단 정보를 반환합니다.

    ## 카카오 챗봇 연결 정보
    ---
    - 동작 방식: 발화
        - "중식 등록"
        - "석식 등록"

    - OpenBuilder:
        - 블럭:
            - "식단 등록 - 중식"
            - "식단 등록 - 석식"
        - 스킬:
            - "중식 등록"
            - "석식 등록"
    ---

    - Params:
        - detail_params:
            - menu(sys.plugin.text): 등록할 메뉴
    """
    logger.info(
        "식단 등록 요청 수신: user_id=%s, meal_type=%s", payload.user_id, meal_type
    )

    if (
        payload.action.detail_params is None
        or not payload.detail_params
        or "menu" not in payload.detail_params.keys()
    ):
        logger.error(
            "식단 등록 실패: user_id=%s, meal_type=%s, menu=None",
            payload.user_id,
            meal_type,
        )
        return JSONResponse(
            KakaoResponse()
            .add_component(SimpleTextComponent("메뉴를 입력해주세요."))
            .get_dict()
        )
    menu_list = split_string(payload.detail_params["menu"].origin)

    logger.debug(
        "식단 등록 메뉴 리스트 생성: user_id=%s, meal_type=%s, menu_list=%s",
        payload.user_id,
        meal_type,
        menu_list,
    )
    contexts: List[Context] = deepcopy(payload.contexts)
    if meal_type == "lunch":
        contexts = save_menu(
            contexts,
            "lunch_menu",
            restaurant.name,
            menu_list,
            add_mode=True,
        )
    elif meal_type == "dinner":
        contexts = save_menu(
            contexts,
            "dinner_menu",
            restaurant.name,
            menu_list,
            add_mode=True,
        )
    else:
        logger.error(
            "식단 등록 실패: user_id=%s, meal_type=%s, menu_list=%s",
            payload.user_id,
            meal_type,
            menu_list,
        )
        return JSONResponse(
            meal_error_response_maker("식사 종류를 확인해주세요.").get_dict()
        )
    logger.debug(
        "식단 등록 완료: user_id=%s, meal_type=%s, menu_list=%s",
        payload.user_id,
        meal_type,
        menu_list,
    )
    # 등록된 식단 정보를 다시 불러와 카드를 생성
    lunch_menu = extract_menu(contexts, "lunch_menu", restaurant.name)
    dinner_menu = extract_menu(contexts, "dinner_menu", restaurant.name)

    lunch_meal = MealCard(
        menu=lunch_menu,
        meal_type=MealType.lunch,
        restaurant_name=restaurant.name,
    )
    dinner_meal = MealCard(
        menu=dinner_menu,
        meal_type=MealType.dinner,
        restaurant_name=restaurant.name,
    )
    lunch, dinner = make_meal_cards(lunch_meal, dinner_meal)
    response = meal_response_maker(lunch, dinner)
    response.contexts = contexts

    logger.info("식단 등록 완료: user_id=%s, meal_type=%s", payload.user_id, meal_type)
    for ctx in contexts:
        logger.debug(
            "등록된 %s 식단 menu: %s",
            ctx.name,
            (
                ctx.params.get("menu_list").value
                if ctx.params.get("menu_list")
                else None
            ),
        )
    logger.debug("등록된 식당 이름: restaurant_name: %s", restaurant.name)
    return JSONResponse(response.get_dict())


@meal_router.post(
    "/submit",
    openapi_extra=create_openapi_extra(
        client_extra={
            "restaurant_name": "산돌식당",
        },
    ),
)
@sync_required()
async def meal_submit(
    payload: Annotated[Payload, Depends(parse_payload)],
    client: Annotated[XUserIDClient, Depends(get_xuser_client_by_payload)],
    user: Annotated[User, Depends(get_current_user)],
    restaurant: Annotated[
        RestaurantResponse,
        Depends(select_restaurant),
    ],
):
    """식단 정보를 확정하는 API입니다.

    임시 저장된 식단 정보를 확정하고 등록합니다.

    ## 카카오 챗봇 연결 정보
    ---
    - 동작방식: 버튼 연결

    - OpenBuilder:
        - 블럭: "식단 확정"
        - 스킬: "식단 확정"
    ---

    Returns:
        str: 확정된 식단 정보를 반환합니다.
    """
    # 요청을 받아 Payload 객체로 변환 및 사용자의 ID로 등록된 식당 객체를 불러옴
    logger.info("식단 확정 요청 수신: user_id=%s", payload.user_id)

    contexts: List[Context] = deepcopy(payload.contexts)
    lunch_menu = extract_menu(contexts, "lunch_menu", restaurant.name)
    dinner_menu = extract_menu(contexts, "dinner_menu", restaurant.name)

    # 식당 정보를 확정 등록
    results = await asyncio.gather(
        post_meal(MealType.lunch, lunch_menu, restaurant.id, client),
        post_meal(MealType.dinner, dinner_menu, restaurant.id, client),
        return_exceptions=True,
    )

    # 예외 여부 확인 및 메시지 작성
    errors = []
    for meal_type, result in zip(
        [MealType.lunch, MealType.dinner], results, strict=False
    ):
        if isinstance(result, Exception):
            logger.error(
                "식단 확정 실패: user_id=%s, restaurant_name=%s, meal_type=%s, error=%s",
                payload.user_id,
                restaurant.name,
                meal_type.value,
                repr(result),
            )
            if isinstance(result, HTTPStatusError):
                errors.append(
                    f"{meal_type.value} 등록 실패 (상태 코드: {result.response.status_code})"
                )
            else:
                errors.append(f"{meal_type.value} 등록 중 알 수 없는 오류 발생")

    if errors:
        return JSONResponse(
            KakaoResponse()
            .add_component(
                SimpleTextComponent("\n".join(errors) + "\n확인 후 다시 시도해주세요.")
            )
            .get_dict()
        )

    # 확정된 식당 정보를 다시 불러와 카드를 생성
    latest_meals: list[MealResponse] = await fetch_latest_meals(client, restaurant.id)
    lunch = [meal for meal in latest_meals if meal.meal_type == MealType.lunch][0]
    dinner = [meal for meal in latest_meals if meal.meal_type == MealType.dinner][0]
    lunch_carousel, dinner_carousel = make_meal_cards(lunch, dinner)

    # 응답 생성
    response = KakaoResponse()
    submit_message = SimpleTextComponent(
        "식단 정보가 아래 내용으로 확정 등록되었습니다."
    )
    response.add_component(submit_message)
    response.add_component(lunch_carousel)
    response.add_component(dinner_carousel)
    contexts = save_menu(
        contexts,
        "lunch_menu",
        restaurant.name,
        [],
        lifspan=0,
        ttl=0,
    )
    contexts = save_menu(
        contexts,
        "dinner_menu",
        restaurant.name,
        [],
        lifspan=0,
        ttl=0,
    )
    response.contexts = contexts
    logger.info(
        "식단 확정 완료: user_id=%s, restaurant_name=%s",
        payload.user_id,
        restaurant.name,
    )
    return JSONResponse(response.get_dict())
