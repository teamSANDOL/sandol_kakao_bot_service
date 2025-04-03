from typing import Annotated
from datetime import datetime
from enum import Enum
from pydantic import BaseModel

from app.schemas.base import Timestamp

class MealType(str, Enum):
    """식사 종류를 나타내는 Enum 클래스

    Attributes:
        breakfast (str): 아침 식사
        brunch (str): 브런치
        lunch (str): 점심 식사
        dinner (str): 저녁 식사
    """

    breakfast = "breakfast"
    brunch = "brunch"
    lunch = "lunch"
    dinner = "dinner"


class BaseMeal(BaseModel):
    """공통 Meal 모델

    Attributes:
        menu (list[str]): 메뉴 목록
        meal_type (MealType): 식사 종류
    """

    menu: list[str]
    meal_type: MealType

class MealResponse(BaseMeal):
    """개별 식사 응답 모델

    Attributes:
        id (int): 식사 ID
        registered_at (Timestamp): 등록 시간
        restaurant_id (int): 식당 ID
        restaurant_name (str): 식당 이름
        updated_at (Timestamp): 수정 시간
    """

    id: int
    registered_at: Timestamp
    restaurant_id: int
    restaurant_name: str
    updated_at: Timestamp
