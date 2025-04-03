from datetime import datetime

from kakao_chatbot import Payload
from kakao_chatbot.response import KakaoResponse
from kakao_chatbot.response.components import (
    ItemCardComponent,
    CarouselComponent,
    TextCardComponent,
    SimpleTextComponent,
    ListCardComponent,
)

from app.schemas.meals import MealResponse
from app.utils import get_korean_day
from app.config import BlockID


def make_meal_card(
    meal: MealResponse
) -> ItemCardComponent | TextCardComponent:
    """식당의 식단 정보를 TextCard 형식으로 반환합니다.

    식당 객체의 식단 정보를 받아 TextCardComponent 객체를 생성하여 반환합니다.
    만약 메뉴가 없을 경우 "식단 정보가 없습니다."를 반환합니다.

    Args:
        meal (MealResponse): 식당 객체
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
    meals: list[MealResponse]
) -> tuple[CarouselComponent, CarouselComponent]:
    """주어진 식단 정보를 바탕으로 점심과 저녁 식단을 각각 Carousel로 생성합니다.

    각 식당에 대해 점심과 저녁 식단 정보를 추가합니다.
    점심과 저녁 식단은 각각 CarouselComponent로 생성되며,
    각 식당의 식단 정보는 ItemCardComponent로 표현됩니다.
    식단 정보가 없는 경우에는 "식단 정보가 없습니다."라는 메시지를 포함합니다.

    Args:
        meals (list[MealResponse]): 식단 정보 리스트

    Returns:
        tuple[Carousel, Carousel]: 점심 Carousel, 저녁 Carousel
    """
    lunch = CarouselComponent()
    dinner = CarouselComponent()

    # 각 식당에 대해 점심과 저녁 식단 정보를 추가
    for meal in meals:
        lunch.add_item(make_meal_card("lunch", meal))
        dinner.add_item(make_meal_card("dinner", meal))

    return lunch, dinner
