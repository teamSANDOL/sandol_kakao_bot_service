from typing import List, Optional

from app.config import Config
from app.schemas.meals import MealType, MealResponse, RestaurantResponse
from app.utils.http import XUserIDClient


async def fetch_latest_meals(
    client: XUserIDClient,
    restaurant_id: Optional[int] = None,
) -> List[MealResponse]:
    """식사 정보를 가져오는 함수

    Args:
        client (XUserIDClient): HTTP 클라이언트 인스턴스
        restaurant_id (int, optional): 식당 ID. 기본값은 None.
            None인 경우 모든 식사 정보를 가져옵니다.
            특정 식당의 식사 정보를 가져오려면 해당 식당 ID를 제공해야 합니다.

    Returns:
        List[MealResponse]: 식사 정보 리스트
    """
    if not restaurant_id:
        response = await client.get(f"{Config.MEAL_SERVICE_URL}/api/meals/latest")
    else:
        response = await client.get(
            (f"{Config.MEAL_SERVICE_URL}/meals/restaurants/{{restaurant_id}}latest")
        )
    response.raise_for_status()
    list_data = response.json().get("data", [])

    # Pydantic 모델을 사용하여 JSON 데이터를 직접 변환
    return [MealResponse.model_validate(item) for item in list_data]


async def fetch_restaurants(
    client: XUserIDClient,
    restaurant_id: Optional[int] = None,
) -> List[RestaurantResponse]:
    """식당 정보를 가져오는 함수

    Args:
        client (XUserIDClient): HTTP 클라이언트 인스턴스

    Returns:
        List[RestaurantResponse]: 식당 정보 리스트
    """
    if not restaurant_id:
        response = await client.get(f"{Config.MEAL_SERVICE_URL}/api/restaurants")
    else:
        response = await client.get(
            (f"{Config.MEAL_SERVICE_URL}/restaurants/{{restaurant_id}}")
        )
    response.raise_for_status()
    list_data = response.json().get("data", [])

    # Pydantic 모델을 사용하여 JSON 데이터를 직접 변환
    return [RestaurantResponse.model_validate(item) for item in list_data]


async def fetch_restaurant_by_name(
    name: str,
    client: XUserIDClient,
) -> Optional[RestaurantResponse]:
    """식당 이름으로 식당을 검색하여 반환합니다 (부분 일치)."""
    response = await client.get(
        f"{Config.MEAL_SERVICE_URL}/restaurants/", params={"name": name, "size": 1}
    )
    response.raise_for_status()
    data = response.json().get("data", [])
    if data:
        return RestaurantResponse.model_validate(data[0])
    return None


async def fetch_my_restaurants(
    user_id: int,
    client: XUserIDClient,
) -> List[RestaurantResponse]:
    """사용자가 관리자 또는 소유자로 등록된 식당들을 조회합니다."""
    response = await client.get(
        f"{Config.MEAL_SERVICE_URL}/restaurants/",
        params={"owner_id": user_id, "manager_id": user_id, "size": 100},
    )
    response.raise_for_status()
    data = response.json().get("data", [])
    return [RestaurantResponse.model_validate(item) for item in data]


async def post_meal(
    meal_type: MealType,
    menu: list[str],
    restaurant_id: int,
    client: XUserIDClient,
) -> bool:
    """식단 정보를 등록합니다.

    Args:
        meal_type (MealType): 식사 종류 (중식 또는 석식)
        menu (list[str]): 메뉴
        restaurant_id (int): 식당 ID
        client (XUserIDClient): HTTP 클라이언트 인스턴스

    Returns:
        dict: 등록된 식단 정보
    """
    response = await client.post(
        f"{Config.MEAL_SERVICE_URL}/api/meals/{restaurant_id}",
        json={
            "meal_type": meal_type,
            "menu": menu,
        },
    )
    response.raise_for_status()
    return response.status_code == Config.HttpStatus.CREATED
