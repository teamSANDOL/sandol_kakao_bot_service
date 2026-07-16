"""식단 응답 조합, 컨텍스트 저장, 식당 선택 관련 유틸 함수 모음입니다."""

from collections.abc import Sequence
import json
import re
from datetime import datetime, timezone
from typing import Annotated, List, Optional, overload

from fastapi import Depends
from fastapi.responses import JSONResponse
from kakao_chatbot import Payload
from kakao_chatbot.context import Context, ContextParam
from kakao_chatbot.response import KakaoResponse
from kakao_chatbot.response.components import (
    CarouselComponent,
    TextCardComponent,
    SimpleTextComponent,
)

from app.config import BlockID, logger
from app.config.blocks import get_cafeteria_register_quick_replies
from app.models.users import User
from app.config import Config
from app.schemas.meals import MealCard, MealResponse, RestaurantResponse, TimeRange
from app.services.meal_service import fetch_my_restaurants
from app.services.user_service import get_current_user, get_xuser_client_by_payload
from app.utils import get_korean_day
from app.utils.http import XUserIDClient
from app.utils.kakao import KakaoError, extract_text_value, parse_payload


MENU_CONTEXT_ERROR_MESSAGE = (
    "혹시 중식, 석식을 고르셨나요? 아직 고르지 않으셨다면 '메뉴등록'을 입력한 뒤 "
    "어떤 종류의 메뉴를 등록하실지 선택해주세요! 만약, 올바르게 선택하신 뒤에도 "
    "이 메시지가 계속해서 나온다면 운영진에게 연락해주세요."
)


def make_meal_card(meal: MealCard) -> TextCardComponent:
    """식당의 식단 정보를 TextCard 형식으로 반환합니다.

    식당 객체의 식단 정보를 받아 TextCardComponent 객체를 생성하여 반환합니다.
    만약 메뉴가 없을 경우 "식단 정보가 없습니다."를 반환합니다.

    Args:
        meal (MealCard): 식당 객체
    """
    # 식사 종류를 한글로 변환하기 위한 딕셔너리
    mealtype_dict = {"lunch": "점심", "dinner": "저녁"}

    # 카드 제목 예: "산돌식당(점심)"
    title = f"{meal.restaurant_name}({mealtype_dict[meal.meal_type]})"
    r_t: datetime = meal.updated_at
    formatted_time = r_t.strftime(
        (
            f"\n{r_t.month}월 {r_t.day}일 {get_korean_day(r_t.weekday())}요일 "
            f"{r_t.hour}시 업데이트"
        )
    )

    # 메뉴 리스트를 개행문자로 연결하여 반환
    # "메뉴1\n메뉴2\n메뉴3" 또는 "식단 정보가 없습니다."
    description = "\n".join(meal.menu) if meal.menu else "식단 정보가 없습니다."

    description += formatted_time
    textcard = TextCardComponent(title=title, description=description)
    textcard.add_button(
        label="식당 정보 보기",
        action="block",
        block_id=BlockID.RESTAURANT_INFO,
        extra={"restaurant_name": meal.restaurant_name},
    )
    return textcard


def make_meal_cards(
    lunch_meal: MealCard | Sequence[MealCard],
    dinner_meal: MealCard | Sequence[MealCard],
) -> tuple[CarouselComponent, CarouselComponent]:
    """점심과 저녁 식단 정보를 CarouselComponent로 생성합니다.

    점심과 저녁 식단 정보를 받아 각각의 CarouselComponent를 생성합니다.
    만약 식단 정보가 없을 경우 "식단 정보가 없습니다."라는 카드가 추가됩니다.

    Args:
        lunch_meal (MealCard | list[MealCard]): 점심 식단 정보
        dinner_meal (MealCard | list[MealCard]): 저녁 식단 정보

    Returns:
        tuple[CarouselComponent, CarouselComponent]: 점심과 저녁 식단 정보를 담은 CarouselComponent
    """

    def create_carousel(
        meals: MealCard | Sequence[MealCard], meal_type: str
    ) -> CarouselComponent:
        """특정 식사 타입의 CarouselComponent를 생성합니다."""
        mealtype_dict = {"lunch": "점심", "dinner": "저녁"}
        carousel = CarouselComponent()
        if isinstance(meals, MealCard):
            meals = [meals]

        for meal in meals:
            if meal:
                carousel.add_item(make_meal_card(meal))

        if carousel.is_empty:
            carousel.add_item(
                TextCardComponent(
                    title=f"{mealtype_dict[meal_type]}",
                    description="식단 정보가 없습니다.",
                )
            )

        return carousel

    lunch_carousel = create_carousel(lunch_meal, "lunch")
    dinner_carousel = create_carousel(dinner_meal, "dinner")

    return lunch_carousel, dinner_carousel


def normalize_meal_datetime(value: datetime) -> datetime:
    """식단 시각을 서비스 타임존 기준으로 정규화합니다."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc).astimezone(Config.TZ)
    return value.astimezone(Config.TZ)


def sort_meals_for_display(
    meals: list[MealResponse],
    student_restaurant_ids: set[int],
) -> list[MealResponse]:
    """카카오 식단 노출 규칙에 맞춰 식당 순서를 정렬합니다."""
    today = datetime.now(tz=Config.TZ).date()
    today_meals: list[MealResponse] = []
    older_meals: list[MealResponse] = []

    for meal in meals:
        registered_at = normalize_meal_datetime(meal.registered_at)
        if registered_at.date() == today:
            today_meals.append(meal)
        else:
            older_meals.append(meal)

    today_meals.sort(
        key=lambda meal: (
            meal.restaurant_id in student_restaurant_ids,
            normalize_meal_datetime(meal.registered_at),
        )
    )
    older_meals.sort(
        key=lambda meal: normalize_meal_datetime(meal.registered_at),
        reverse=True,
    )

    return today_meals + older_meals


SPECIAL_DELIMITER_PATTERNS = [r",\s*", r";", r":", r"\|", r"-", r"/"]
SPECIAL_DELIMITER_REGEX = re.compile("|".join(SPECIAL_DELIMITER_PATTERNS))


def split_string(s: str) -> list[str]:
    """문자열을 구분자를 기준으로 분리하여 리스트로 반환합니다.

    문자열을 받아 여러 구분자를 기준으로 분리하여 리스트로 반환합니다.
    구분자는 콤마, 세미콜론, 콜론, 파이프, 대시, 슬래시입니다.

    Args:
        s (str): 분리할 문자열

    Returns:
        list: 분리된 문자열 리스트
    """
    if SPECIAL_DELIMITER_REGEX.search(s):
        modified_str = SPECIAL_DELIMITER_REGEX.sub("\n", s)
        return [item.strip() for item in modified_str.split("\n") if item.strip()]

    return [item.strip() for item in re.split(r"\s+", s) if item.strip()]


@overload
def time_range_to_string(
    start: datetime,
    end: datetime,
) -> str:
    pass


@overload
def time_range_to_string(
    time_range: TimeRange,
) -> str:
    pass


def time_range_to_string(  # noqa: D417
    *args,
    **kwargs,
) -> str:
    """시간 범위를 문자열로 변환합니다.

    Args:
        start (datetime): 시작 시간
        end (datetime): 종료 시간
        time_range (TimeRange): TimeRange 객체

    Returns:
        str: 변환된 문자열
    """
    if len(args) == 2 or "start" in kwargs and "end" in kwargs:  # noqa: PLR2004
        start, end = args if len(args) == 2 else (kwargs["start"], kwargs["end"])  # noqa: PLR2004
        return f"{start.strftime('%H:%M')} ~ {end.strftime('%H:%M')}"
    if len(args) == 1 and isinstance(args[0], TimeRange) or "time_range" in kwargs:
        time_range = args[0] if len(args) == 1 else kwargs["time_range"]
        if isinstance(time_range, TimeRange):
            time_range.to_string()
            return f"{time_range.start} ~ {time_range.end}"
        return f"{time_range.start} ~ {time_range.end}"
    return ""


def extract_menu(contexts, meal_type_name, restaurant_name) -> list[str]:
    """컨텍스트에서 메뉴 리스트를 추출합니다.

    Args:
        contexts (list[Context]): 컨텍스트 리스트입니다.
        meal_type_name (str): 식사 종류 이름입니다.
        restaurant_name (str): 식당 이름입니다.

    Returns:
        list: 추출된 메뉴 리스트입니다.
    """
    logger.debug("메뉴 타입 추출\n식사 종류: %s", meal_type_name)
    context: Optional[Context] = next(
        (ctx for ctx in contexts if ctx.name == meal_type_name), None
    )
    logger.debug("컨텍스트: %s", context.name if context else "없음")
    if (
        context
        and isinstance(context.params.get("menu_list"), ContextParam)
        and isinstance(context.params.get("restaurant_name"), ContextParam)
        and context.params["restaurant_name"].value == restaurant_name
    ):
        menu_list = json.loads(context.params["menu_list"].value)
        logger.info(
            "메뉴 context 추출 성공: meal_type_context=%s, requested_restaurant=%s, "
            "context_restaurant=%s, menu_count=%d, menu=%s, lifespan=%s, ttl=%s",
            meal_type_name,
            restaurant_name,
            context.params["restaurant_name"].value,
            len(menu_list),
            menu_list,
            context.lifespan,
            context.ttl,
        )
        return menu_list
    logger.warning(
        "메뉴 타입 추출 실패\n식사 종류: %s\n식당 이름: %s \n컨텍스트: %s \n컨텍스트 param: %s \n컨텍스트 menu_list: %s",
        meal_type_name,
        restaurant_name,
        context.name if context else "없음",
        context.params if context and context.params else "없음",
        context.params.get("menu_list") if context and context.params else "없음",
    )
    return []


def summarize_menu_contexts(contexts: list[Context]) -> list[dict[str, object]]:
    """식단 등록 context를 INFO 로그에 남기기 좋은 형태로 요약합니다."""
    summaries: list[dict[str, object]] = []
    for context in contexts:
        if context.name not in {"lunch_menu", "dinner_menu"}:
            continue

        menu_list_param = context.params.get("menu_list")
        restaurant_name_param = context.params.get("restaurant_name")
        menu_items: list[str] = []
        if isinstance(menu_list_param, ContextParam):
            try:
                parsed_menu = json.loads(menu_list_param.value)
            except json.JSONDecodeError:
                parsed_menu = []
            if isinstance(parsed_menu, list):
                menu_items = [str(item) for item in parsed_menu]

        restaurant_name = ""
        if isinstance(restaurant_name_param, ContextParam):
            restaurant_name = extract_text_value(restaurant_name_param.value) or ""

        summaries.append(
            {
                "context": context.name,
                "restaurant_name": restaurant_name,
                "menu_count": len(menu_items),
                "menu": menu_items,
                "lifespan": context.lifespan,
                "ttl": context.ttl,
            }
        )
    return summaries


def has_menu_context(
    contexts: list[Context], meal_type_name: str, restaurant_name: str
) -> bool:
    """컨텍스트에 특정 식사 종류 메뉴 정보가 실제로 존재하는지 확인합니다.

    Args:
        contexts (list[Context]): 컨텍스트 리스트입니다.
        meal_type_name (str): 식사 종류 이름입니다.
        restaurant_name (str): 식당 이름입니다.

    Returns:
        bool: 해당 식당의 메뉴 컨텍스트가 있으면 True입니다.
    """
    context: Optional[Context] = next(
        (ctx for ctx in contexts if ctx.name == meal_type_name), None
    )
    if not context:
        logger.info(
            "메뉴 context 확인 실패: reason=missing_context, "
            "meal_type_context=%s, requested_restaurant=%s, available_contexts=%s",
            meal_type_name,
            restaurant_name,
            [context.name for context in contexts],
        )
        return False

    menu_list_param = context.params.get("menu_list")
    restaurant_name_param = context.params.get("restaurant_name")
    if not isinstance(menu_list_param, ContextParam):
        logger.info(
            "메뉴 context 확인 실패: reason=missing_menu_list, "
            "meal_type_context=%s, requested_restaurant=%s, context_params=%s",
            meal_type_name,
            restaurant_name,
            context.params,
        )
        return False
    if not isinstance(restaurant_name_param, ContextParam):
        logger.info(
            "메뉴 context 확인 실패: reason=missing_restaurant_name, "
            "meal_type_context=%s, requested_restaurant=%s, context_params=%s",
            meal_type_name,
            restaurant_name,
            context.params,
        )
        return False

    has_context = bool(
        context
        and menu_list_param
        and restaurant_name_param.value == restaurant_name
    )
    if has_context:
        logger.info(
            "메뉴 context 확인 성공: meal_type_context=%s, requested_restaurant=%s, "
            "context_restaurant=%s, menu_value=%s, lifespan=%s, ttl=%s",
            meal_type_name,
            restaurant_name,
            restaurant_name_param.value,
            menu_list_param.value,
            context.lifespan,
            context.ttl,
        )
    else:
        logger.info(
            "메뉴 context 확인 실패: reason=restaurant_mismatch, "
            "meal_type_context=%s, requested_restaurant=%s, context_restaurant=%s, "
            "menu_value=%s",
            meal_type_name,
            restaurant_name,
            restaurant_name_param.value,
            menu_list_param.value,
        )
    return has_context


def save_menu(  # noqa: PLR0913
    contexts: list[Context],
    meal_type_name: str,
    restaurant_name: str,
    menu_list: list[str],
    lifespan: int = 5,
    ttl: int = 300,
    add_mode: bool = False,
) -> list[Context]:
    """메뉴를 저장하는 함수입니다.

    Args:
        contexts (list[Context]): 컨텍스트 리스트입니다.
        meal_type_name (str): 식사 종류 이름입니다.
        restaurant_name (str): 식당 이름입니다.
        menu_list (list): 저장할 메뉴 리스트입니다.
        lifespan (int, optional): 컨텍스트의 생명주기입니다. 기본값은 5입니다.
        ttl (int, optional): 컨텍스트의 TTL입니다. 기본값은 300입니다.
        add_mode (bool, optional): 메뉴 추가 모드 여부입니다. 기본값은 False입니다.
        만약 True인 경우 기존 메뉴에 추가됩니다.
        False인 경우 기존 메뉴가 삭제되고 새로운 메뉴가 저장됩니다.

    Returns:
        list[Context]: 저장된 메뉴 리스트입니다.
    """
    logger.info(
        "식단 context 저장 시작: meal_type_context=%s, restaurant_name=%s, "
        "menu_count=%d, menu=%s, add_mode=%s, lifespan=%d, ttl=%d",
        meal_type_name,
        restaurant_name,
        len(menu_list),
        menu_list,
        add_mode,
        lifespan,
        ttl,
    )
    logger.debug("메뉴 저장\n식사 종류: %s", meal_type_name)
    context: Optional[Context] = next(
        (ctx for ctx in contexts if ctx.name == meal_type_name), None
    )
    logger.debug("컨텍스트: %s", context.name if context else "없음")
    if context:
        # 기존 메뉴가 있는 경우 삭제
        if add_mode and isinstance(context.params.get("menu_list"), ContextParam):
            # 메뉴 추가 모드인 경우 기존 메뉴에 추가
            previous_menu = json.loads(context.params["menu_list"].value)
            previous_restaurant_name_param = context.params.get("restaurant_name")
            logger.info(
                "식단 context 기존 값 확인: meal_type_context=%s, "
                "previous_restaurant_name=%s, previous_menu_count=%d, "
                "previous_menu=%s, previous_lifespan=%s, previous_ttl=%s",
                meal_type_name,
                previous_restaurant_name_param.value
                if isinstance(previous_restaurant_name_param, ContextParam)
                else None,
                len(previous_menu),
                previous_menu,
                context.lifespan,
                context.ttl,
            )
            menu_list = json.loads(context.params["menu_list"].value) + menu_list
            logger.info(
                "식단 context 기존 메뉴 병합: meal_type_context=%s, "
                "restaurant_name=%s, merged_menu_count=%d, merged_menu=%s",
                meal_type_name,
                restaurant_name,
                len(menu_list),
                menu_list,
            )
        contexts.remove(context)
        menu_str = json.dumps(menu_list, ensure_ascii=False)
        new_context = Context(
            name=meal_type_name,
            params={
                "menu_list": ContextParam(menu_str, menu_str),
                "restaurant_name": ContextParam(restaurant_name, restaurant_name),
            },
            lifespan=lifespan,
            ttl=ttl,
        )
        contexts.append(new_context)
        logger.info(
            "식단 context 저장 완료: meal_type_context=%s, restaurant_name=%s, "
            "menu_count=%d, contexts=%s",
            meal_type_name,
            restaurant_name,
            len(menu_list),
            summarize_menu_contexts(contexts),
        )
    else:
        logger.error(
            "식단 context 저장 실패: meal_type_context=%s, restaurant_name=%s, "
            "available_contexts=%s",
            meal_type_name,
            restaurant_name,
            [context.name for context in contexts],
        )
        raise KakaoError(MENU_CONTEXT_ERROR_MESSAGE)
    return contexts


# 식당 유형을 문자열로 변환하기 위한 딕셔너리 (전역 변수로 정의)
ESTABLISHMENT_TYPE_DICT = {
    "student": "학생식당",
    "fixed_menu_restaurant": "고정메뉴 일반식당",
    "fixed_korean_buffet": "고정메뉴형 한식뷔페",
    "variable_korean_buffet": "메뉴 변경형 한식뷔페",
}


def establishment_type_to_string(establishment_type: str) -> str:
    """식당의 유형을 문자열로 변환합니다.

    Args:
        establishment_type (str): 식당의 유형

    Returns:
        str: 변환된 문자열
    """
    return ESTABLISHMENT_TYPE_DICT.get(establishment_type, establishment_type)


def meal_response_maker(
    lunch: CarouselComponent,
    dinner: CarouselComponent,
    is_temp: bool = True,
    restaurant_name: str | None = None,
) -> KakaoResponse:
    """식단 정보 미리보기를 반환하는 응답을 생성합니다.

    Args:
        lunch (CarouselComponent): 점심 식단 카드
        dinner (CarouselComponent): 저녁 식단 카드
        is_temp (bool): 임시 응답 여부
            True인 경우, "식단 미리보기"라는 제목이 추가됩니다.
            False인 경우, 제목이 추가되지 않습니다.
        restaurant_name (str | None): QuickReply에 보존할 식당 이름입니다.

    Returns:
        KakaoResponse: 식단 정보 미리보기 응답
    """
    response = KakaoResponse()
    if is_temp:
        response += SimpleTextComponent("식단 미리보기")
    response += lunch
    response += dinner
    quick_replies = get_cafeteria_register_quick_replies(restaurant_name)
    logger.info(
        "식단 등록 응답 QuickReply 생성: is_temp=%s, restaurant_name=%s, "
        "quick_replies=%s",
        is_temp,
        restaurant_name,
        [
            {
                "label": quick_reply.label,
                "block_id": quick_reply.block_id,
                "extra": quick_reply.extra,
            }
            for quick_reply in quick_replies
        ],
    )
    for quick_reply in quick_replies:
        response.add_quick_reply(quick_reply)
    return response


def meal_error_response_maker(
    message: str, restaurant_name: str | None = None
) -> KakaoResponse:
    """식단 정보 에러 메시지를 반환하는 응답을 생성합니다.

    Args:
        message (str): 에러 메시지
        restaurant_name (str | None): QuickReply에 보존할 식당 이름입니다.

    Returns:
        KakaoResponse: 에러 메시지 응답
    """
    response = KakaoResponse()
    simple = SimpleTextComponent(message)
    response.add_component(simple)
    quick_replies = get_cafeteria_register_quick_replies(restaurant_name)
    logger.info(
        "식단 등록 에러 응답 QuickReply 생성: message=%s, restaurant_name=%s, "
        "quick_replies=%s",
        message,
        restaurant_name,
        [
            {
                "label": quick_reply.label,
                "block_id": quick_reply.block_id,
                "extra": quick_reply.extra,
            }
            for quick_reply in quick_replies
        ],
    )
    for quick_reply in quick_replies:
        response.add_quick_reply(quick_reply)

    return response


def extract_restaurant_name_from_menu_contexts(contexts: list[Context]) -> str:
    """식단 등록 context에서 식당 이름을 추출합니다."""
    restaurant_names: list[str] = []
    for context in contexts:
        if context.name not in {"lunch_menu", "dinner_menu"}:
            continue
        restaurant_name_param = context.params.get("restaurant_name")
        if not isinstance(restaurant_name_param, ContextParam):
            continue
        restaurant_name = extract_text_value(restaurant_name_param.value)
        if restaurant_name and restaurant_name not in restaurant_names:
            restaurant_names.append(restaurant_name)

    if len(restaurant_names) == 1:
        return restaurant_names[0]
    return ""


async def get_my_restaurants(
    user: Annotated[User, Depends(get_current_user)],
    client: Annotated[XUserIDClient, Depends(get_xuser_client_by_payload)],
) -> list[RestaurantResponse]:
    """DI에 의존하는 식당 정보를 가져오는 함수.

    Args:
        user (User): 현재 사용자
        client (XUserIDClient): 비동기 HTTP 클라이언트
    Returns:
        list[RestaurantResponse]: 사용자의 식당 정보 리스트
    """
    return await fetch_my_restaurants(user.keycloak_id, client)


async def select_restaurant(
    payload: Annotated[Payload, Depends(parse_payload)],
    user: Annotated[User, Depends(get_current_user)],
    client: Annotated[XUserIDClient, Depends(get_xuser_client_by_payload)],
    restaurants: Annotated[
        List[RestaurantResponse],
        Depends(get_my_restaurants),
    ],
) -> RestaurantResponse | JSONResponse:
    """식당을 선택합니다.

    식당이 여러개일 경우 사용자가 선택할 수 있도록 합니다.
    사용자가 선택한 식당에 따라 식당을 관리합니다.

    Args:
        payload (Payload): 카카오 챗봇에서 전달된 Payload 객체입니다.
        user (User): 현재 사용자 객체입니다.
        client (XUserIDClient): XUserIDClient 객체입니다.
        restaurants (RestaurantResponse | List[RestaurantResponse]):
            등록된 식당 정보입니다.

    Returns:
        RestaurantResponse: 등록된 식단 정보를 반환합니다.
        JSONResponse: 등록된 식단 정보를 반환합니다.
    """
    logger.info(
        "식당 선택\n사용자: %s\n식당 리스트: %s",
        user.kakao_id,
        [restaurant.name for restaurant in restaurants],
    )
    restaurant_name = extract_text_value(
        payload.action.client_extra.get("restaurant_name")
    )
    restaurant_name_source = "client_extra" if restaurant_name else ""
    if not restaurant_name:
        restaurant_name = extract_restaurant_name_from_menu_contexts(payload.contexts)
        restaurant_name_source = "menu_context" if restaurant_name else ""
    logger.info(
        "식당 선택 입력 확인: user_id=%s, restaurant_name=%s, source=%s, "
        "menu_contexts=%s",
        payload.user_id,
        restaurant_name or None,
        restaurant_name_source or "not_found",
        summarize_menu_contexts(payload.contexts),
    )
    if restaurant_name:
        # 사용자가 선택한 식당이 있는 경우
        for restaurant in restaurants:
            if restaurant.name == restaurant_name:
                logger.info(
                    "식당 선택 완료: user_id=%s, restaurant_id=%s, "
                    "restaurant_name=%s, source=%s",
                    payload.user_id,
                    restaurant.id,
                    restaurant.name,
                    restaurant_name_source,
                )
                return restaurant
        logger.info(
            "식당 선택 후보 불일치: user_id=%s, requested_restaurant_name=%s, "
            "source=%s, candidates=%s",
            payload.user_id,
            restaurant_name,
            restaurant_name_source,
            [
                {"restaurant_id": restaurant.id, "restaurant_name": restaurant.name}
                for restaurant in restaurants
            ],
        )

    if len(restaurants) == 1:
        logger.info(
            "식당 단일 후보 자동 선택: user_id=%s, restaurant_id=%s, "
            "restaurant_name=%s",
            payload.user_id,
            restaurants[0].id,
            restaurants[0].name,
        )
        return restaurants[0]

    logger.info(
        "사용자에게 식당 선택을 요청합니다.\n식당 목록: %s",
        [restaurant.name for restaurant in restaurants],
    )

    response = KakaoResponse()
    if payload.flow is None:
        logger.error(
            "식당 선택 요청 생성 실패: reason=missing_payload_flow, user_id=%s, "
            "candidates=%s",
            payload.user_id,
            [
                {"restaurant_id": restaurant.id, "restaurant_name": restaurant.name}
                for restaurant in restaurants
            ],
        )
        raise KakaoError(response)
    text_card = TextCardComponent(
        title="식당 선택",
        description="식당을 선택하세요.",
    )
    for restaurant in restaurants:
        response.add_quick_reply(
            label=restaurant.name,
            action="block",
            block_id=payload.flow.last_block.id,
            extra={"restaurant_name": restaurant.name},
        )

    response.add_component(text_card)
    raise KakaoError(response)
