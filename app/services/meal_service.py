from typing import List
from httpx import Response

from app.config import Config
from app.schemas.meals import MealType, MealResponse
from app.utils.http import XUserIDClient


async def fetch_latest_meals(
    client: XUserIDClient,
    restaurant_id: int = None,
) -> List[MealResponse]:
    """식사 정보를 가져오는 함수

    Args:
        client (XUserIDClient): HTTP 클라이언트 인스턴스
    Returns:
        List[MealResponse]: 식사 정보 리스트
    """
    if not restaurant_id:
        response = await client.get(f"{Config.MEAL_SERVICE_URL}/meals/latest")
    else:
        response = await client.get(
            (
                f"{Config.MEAL_SERVICE_URL}/"
                "meals/restaurants/{restaurant_id}latest"
            )
        )
    response.raise_for_status()
    list_data = response.json().get("data", [])

    # Pydantic 모델을 사용하여 JSON 데이터를 직접 변환
    data = [MealResponse.model_validate(item) for item in list_data]
    return data
