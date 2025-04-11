from collections.abc import Sequence
import json
import re
from datetime import datetime
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

from app.config import BlockID
from app.config.blocks import get_cafeteria_register_quick_replies
from app.models.user import User
from app.schemas.meals import MealCard, RestaurantResponse, TimeRange
from app.services.meal_service import fetch_my_restaurants
from app.utils import get_korean_day
from app.utils.auth_client import get_xuser_client_by_payload
from app.utils.db import get_current_user
from app.utils.http import XUserIDClient, get_client_by_payload
from app.utils.kakao import parse_payload


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
        meals: MealCard | list[MealCard], meal_type: str
    ) -> CarouselComponent:
        """특정 식사 타입의 CarouselComponent를 생성합니다."""
        carousel = CarouselComponent()
        meals = meals if isinstance(meals, list) else [meals]

        for meal in meals:
            if meal:
                carousel.add_item(make_meal_card(meal))

        if carousel.is_empty:
            carousel.add_item(
                TextCardComponent(
                    title="식단 정보가 없습니다.",
                    description="식단 정보가 없습니다.",
                )
            )

        return carousel

    lunch_carousel = create_carousel(lunch_meal, "lunch")
    dinner_carousel = create_carousel(dinner_meal, "dinner")

    return lunch_carousel, dinner_carousel


def split_string(s: str) -> list[str]:
    """문자열을 구분자를 기준으로 분리하여 리스트로 반환합니다.

    문자열을 받아 여러 구분자를 기준으로 분리하여 리스트로 반환합니다.
    구분자는 콤마, 세미콜론, 콜론, 파이프, 대시, 슬래시입니다.

    Args:
        s (str): 분리할 문자열

    Returns:
        list: 분리된 문자열 리스트
    """
    # 여러 구분자를 개행 문자로 변경
    delimiters = [r",\s*", r";", r":", r"\|", r"-", r"/"]
    regex_pattern = "|".join(delimiters)
    modified_str = re.sub(regex_pattern, "\n", s)

    # 개행 문자가 있는지 확인
    if "\n" in modified_str:
        # 개행 문자를 기준으로 분리하고, 각 항목의 양 끝 공백 제거
        return [item.strip() for item in modified_str.split("\n") if item.strip()]
    # white-space를 기준으로 분리하고, 각 항목의 양 끝 공백 제거
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
            return time_range.to_string()
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
    context: Optional[Context] = next(
        (ctx for ctx in contexts if ctx.name == meal_type_name), None
    )
    if (
        context
        and isinstance(context.params.get("menu_list"), ContextParam)
        and isinstance(context.params.get("restaurant_name"), ContextParam)
        and context.params["restaurant_name"].value == restaurant_name
    ):
        return json.loads(context.params["menu_list"].value)
    return []


def save_menu(
    contexts: list[Context],
    meal_type_name: str,
    restaurant_name: str,
    menu_list: list,
    lifspan: int = 5,
    ttl: int = 300,
) -> list[Context]:
    """메뉴를 저장하는 함수입니다.

    Args:
        contexts (list[Context]): 컨텍스트 리스트입니다.
        meal_type_name (str): 식사 종류 이름입니다.
        restaurant_name (str): 식당 이름입니다.
        menu_list (list): 저장할 메뉴 리스트입니다.

    Returns:
        list[Context]: 저장된 메뉴 리스트입니다.
    """
    context: Optional[Context] = next(
        (ctx for ctx in contexts if ctx.name == meal_type_name), None
    )
    if context:
        # 기존 메뉴가 있는 경우 삭제
        contexts.remove(context)
        menu_str = json.dumps(menu_list, ensure_ascii=False)
        # 새로운 메뉴를 저장
        new_context = Context(
            name=meal_type_name,
            params={
                "menu_list": ContextParam(menu_str, menu_str),
                "restaurant_name": ContextParam(restaurant_name, restaurant_name),
            },
            lifespan=lifspan,
            ttl=ttl,
        )
        contexts.append(new_context)
    return contexts


# 식당 유형을 문자열로 변환하기 위한 딕셔너리 (전역 변수로 정의)
ESTABLISHMENT_TYPE_DICT = {
    "student": "학생식당",
    "vendor": "교내 입점업체",
    "external": "교외 업체",
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
    lunch: CarouselComponent, dinner: CarouselComponent
) -> KakaoResponse:
    """식단 정보 미리보기를 반환하는 응답을 생성합니다.

    Args:
        lunch (CarouselComponent): 점심 식단 카드
        dinner (CarouselComponent): 저녁 식단 카드

    Returns:
        KakaoResponse: 식단 정보 미리보기 응답
    """
    response = KakaoResponse() + SimpleTextComponent("식단 미리보기") + lunch + dinner
    for quick_reply in get_cafeteria_register_quick_replies():
        response.add_quick_reply(quick_reply)
    return response


def meal_error_response_maker(message: str) -> KakaoResponse:
    """식단 정보 에러 메시지를 반환하는 응답을 생성합니다.

    Args:
        message (str): 에러 메시지

    Returns:
        KakaoResponse: 에러 메시지 응답
    """
    response = KakaoResponse()
    simple = SimpleTextComponent(message)
    response.add_component(simple)
    for quick_reply in get_cafeteria_register_quick_replies():
        response.add_quick_reply(quick_reply)

    return response


async def get_my_restaurants(
    user: Annotated[User, Depends(get_current_user)],
    client: Annotated[XUserIDClient, Depends(get_client_by_payload)],
) -> list[RestaurantResponse]:
    """DI에 의존하는 식당 정보를 가져오는 함수

    Args:
        user (User): 현재 사용자
        client (XUserIDClient): 비동기 HTTP 클라이언트
    Returns:
        list[RestaurantResponse]: 사용자의 식당 정보 리스트
    """
    return await fetch_my_restaurants(user.id, client)


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
    restaurant_name: str = payload.action.client_extra.get("restaurant_name", "")
    if restaurant_name:
        # 사용자가 선택한 식당이 있는 경우
        for restaurant in restaurants:
            if restaurant.name == restaurant_name:
                return restaurant

    if len(restaurants) == 1:
        return restaurants[0]

    response = KakaoResponse()

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

    response.add_context(text_card)
    return JSONResponse(response.get_dict())
