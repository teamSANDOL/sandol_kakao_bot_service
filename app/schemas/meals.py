from datetime import datetime
from enum import Enum
from typing import Literal, Optional, Dict
from pydantic import BaseModel


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


class MealRegister(BaseMeal):
    """식사 등록 모델

    BaseMeal을 상속받아 추가적인 필드를 포함하지 않음
    """


class MealCard(BaseMeal):
    """카드를 위해 필요한 정보만 담은 모델

    식사 등록 모델과 유사하지만, 카드에 필요한 정보만 포함

    Attributes:
        restaurant_name (str): 식당 이름
        updated_at (datetime): 업데이트 시간
    """

    restaurant_name: str
    updated_at: datetime = datetime.now()  # 현재 시간으로 초기화


class MealResponse(MealCard):
    """개별 식사 응답 모델

    Attributes:
        id (int): 식사 ID
        registered_at (Timestamp): 등록 시간
        restaurant_id (int): 식당 ID
    """

    id: int
    registered_at: datetime
    restaurant_id: int


class TimeRange(BaseModel):
    """시간 범위를 나타내는 클래스입니다.

    Attributes:
        start (str | datetime): 시작 시간 ("HH:MM" 형식 또는 datetime 객체)
        end (str | datetime): 종료 시간 ("HH:MM" 형식 또는 datetime 객체)
    """

    start: str | datetime  # "HH:MM" 형식
    end: str | datetime  # "HH:MM" 형식

    def to_datetime(self):
        """start와 end 속성을 문자열에서 datetime 객체로 변환합니다."""
        if isinstance(self.start, str):
            self.start = datetime.strptime(self.start, "%H:%M")
        if isinstance(self.end, str):
            self.end = datetime.strptime(self.end, "%H:%M")

    def to_string(self):
        """start와 end 속성을 datetime 객체에서 문자열로 변환합니다."""
        if isinstance(self.start, datetime):
            self.start = self.start.strftime("%H:%M")
        if isinstance(self.end, datetime):
            self.end = self.end.strftime("%H:%M")


class Location(BaseModel):
    """레스토랑의 위치를 나타내는 클래스입니다.

    Attributes:
        is_campus (bool): 캠퍼스 내 위치 여부
        building (Optional[str]): 건물 이름
        map_links (Optional[Dict[str, str]]): 네이버, 카카오 지도 링크
        latitude (Optional[float]): 위도
        longitude (Optional[float]): 경도
    """

    is_campus: bool
    building: Optional[str] = None
    map_links: Optional[Dict[str, str]] = None  # 네이버, 카카오 지도 링크
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class RestaurantSchema(BaseModel):
    """레스토랑의 기본 정보를 나타내는 클래스입니다.

    Attributes:
        name (str): 레스토랑 이름
        establishment_type (Literal["student", "vendor", "external"]): 레스토랑 유형
        location (Optional[Location]): 위치 정보
        opening_time (Optional[TimeRange]): 영업 시간
        break_time (Optional[TimeRange]): 휴식 시간
        breakfast_time (Optional[TimeRange]): 아침 식사 시간
        brunch_time (Optional[TimeRange]): 브런치 시간
        lunch_time (Optional[TimeRange]): 점심 시간
        dinner_time (Optional[TimeRange]): 저녁 시간
    """

    name: str
    establishment_type: Literal["student", "vendor", "external"]
    location: Optional[Location] = None
    opening_time: Optional[TimeRange] = None
    break_time: Optional[TimeRange] = None
    breakfast_time: Optional[TimeRange] = None
    brunch_time: Optional[TimeRange] = None
    lunch_time: Optional[TimeRange] = None
    dinner_time: Optional[TimeRange] = None


class RestaurantResponse(RestaurantSchema):
    """GET /restaurants/{id} 및 /restaurants 엔드포인트 응답 바디를 나타내는 클래스입니다.

    Attributes:
        id (int): 레스토랑 ID
        owner (Optional[int]): 소유자 ID
    """

    id: int
    owner: Optional[int] = None
