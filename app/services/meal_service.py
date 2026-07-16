"""식단/식당 조회 및 등록을 위한 외부 API 연동 서비스입니다."""

from typing import Any, List, Literal, Optional

from httpx import AsyncClient, HTTPStatusError

from app.config import Config, logger
from app.schemas.meals import MealType, MealResponse, RestaurantResponse
from app.utils.http import XUserIDClient


async def fetch_latest_meals(
    client: AsyncClient,
    restaurant_id: Optional[int] = None,
) -> List[MealResponse]:
    """식사 정보를 가져오는 함수.

    Args:
        client (XUserIDClient): HTTP 클라이언트 인스턴스
        restaurant_id (int, optional): 식당 ID. 기본값은 None.
            None인 경우 모든 식사 정보를 가져옵니다.
            특정 식당의 식사 정보를 가져오려면 해당 식당 ID를 제공해야 합니다.

    Returns:
        List[MealResponse]: 식사 정보 리스트
    """
    logger.info("최신 식단 조회 요청 시작: restaurant_id=%s", restaurant_id)
    if not restaurant_id:
        response = await client.get(f"{Config.MEAL_SERVICE_URL}/meals/latest")
    else:
        response = await client.get(
            (f"{Config.MEAL_SERVICE_URL}/meals/restaurant/{restaurant_id}/latest")
        )
    logger.info(
        "최신 식단 조회 응답 수신: restaurant_id=%s, status_code=%s, body=%s",
        restaurant_id,
        response.status_code,
        response.text,
    )
    try:
        response.raise_for_status()
    except HTTPStatusError:
        logger.error(
            "최신 식단 조회 HTTP 오류: restaurant_id=%s, status_code=%s, body=%s",
            restaurant_id,
            response.status_code,
            response.text,
        )
        raise
    list_data = response.json().get("data", [])

    # Pydantic 모델을 사용하여 JSON 데이터를 직접 변환
    logger.debug(f"Fetched meals: {list_data}")
    return [MealResponse.model_validate(item) for item in list_data]


async def fetch_restaurants(
    client: AsyncClient,
    restaurant_id: Optional[int] = None,
    establishment_type: Optional[Literal["student", "fixed_menu_restaurant", "fixed_korean_buffet", "variable_korean_buffet"]] = None,
) -> List[RestaurantResponse]:
    """식당 정보를 가져오는 함수.

    Args:
        client (XUserIDClient): HTTP 클라이언트 인스턴스
        restaurant_id (int, optional): 식당 ID. 기본값은 None.
            None인 경우 모든 식당 정보를 가져옵니다.
            특정 식당의 정보를 가져오려면 해당 식당 ID를 제공해야 합니다.
            식당 ID가 제공되면 해당 식당의 정보만 가져옵니다.
        establishment_type (str, optional): 식당 유형 필터. 기본값은 None.
            None인 경우 모든 식당 유형을 가져옵니다.

    Returns:
        List[RestaurantResponse]: 식당 정보 리스트
    """
    if not restaurant_id:
        params: dict[str, str | int] = {"size": 100}
        if establishment_type is not None:
            params["establishment_type"] = establishment_type
        response = await client.get(
            f"{Config.MEAL_SERVICE_URL}/restaurants/",
            params=params,
        )
    else:
        response = await client.get(
            (f"{Config.MEAL_SERVICE_URL}/restaurants/{restaurant_id}")
        )
    response.raise_for_status()
    data = response.json().get("data")

    if restaurant_id:
        if isinstance(data, dict):
            return [RestaurantResponse.model_validate(data)]
        return []

    if isinstance(data, list):
        return [RestaurantResponse.model_validate(item) for item in data]
    return []


async def fetch_restaurant_by_name(
    name: str,
    client: AsyncClient,
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
    user_id: str,
    client: XUserIDClient,
) -> List[RestaurantResponse]:
    """사용자가 관리자 또는 소유자로 등록된 식당들을 조회합니다.

    Args:
        user_id (str): Keycloak 사용자 `id`.
        client (XUserIDClient): HTTP 클라이언트 인스턴스.

    Returns:
        List[RestaurantResponse]: 사용자가 관련된 식당 정보 리스트.
    """
    logger.info("Fetching restaurants for user_id: %s", user_id)
    params_list: list[dict[str, str]] = [
        {"owner_user_id": user_id},
        {"manager_user_id": user_id},
    ]
    restaurants: list[dict[str, Any]] = []

    for params in params_list:
        response = await client.get(
            f"{Config.MEAL_SERVICE_URL}/restaurants/",
            params=params,
        )
        response.raise_for_status()
        data = response.json().get("data", [])
        logger.info("Fetched %d restaurants with data %s", len(data), data)
        restaurants.extend(data)
    restaurant_responses = [
        RestaurantResponse.model_validate(item) for item in restaurants
    ]
    logger.debug(f"Fetched restaurants response: {restaurant_responses}")
    return restaurant_responses


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
    logger.info(
        "식단 upstream 등록 요청 준비: restaurant_id=%s, meal_type=%s, "
        "raw_menu_count=%d, raw_menu=%s",
        restaurant_id,
        meal_type.value,
        len(menu),
        menu,
    )
    menu_items = [item.strip() for item in menu if item.strip()]
    if not menu_items:
        logger.error(
            "식단 upstream 등록 중단: restaurant_id=%s, meal_type=%s, "
            "reason=empty_menu_after_strip, raw_menu=%s",
            restaurant_id,
            meal_type.value,
            menu,
        )
        raise ValueError("등록할 메뉴가 없습니다.")

    request_body = {
        "meal_type": meal_type,
        "menu": menu_items,
    }
    logger.info(
        "식단 upstream 등록 요청 전송: restaurant_id=%s, meal_type=%s, "
        "menu_count=%d, request_body=%s",
        restaurant_id,
        meal_type.value,
        len(menu_items),
        request_body,
    )
    response = await client.post(
        f"{Config.MEAL_SERVICE_URL}/meals/{restaurant_id}",
        json=request_body,
    )
    logger.info(
        "식단 upstream 등록 응답 수신: restaurant_id=%s, meal_type=%s, "
        "status_code=%s, body=%s",
        restaurant_id,
        meal_type.value,
        response.status_code,
        response.text,
    )
    try:
        response.raise_for_status()
    except HTTPStatusError:
        logger.error(
            "식단 upstream 등록 HTTP 오류: restaurant_id=%s, meal_type=%s, "
            "status_code=%s, body=%s, request_body=%s",
            restaurant_id,
            meal_type.value,
            response.status_code,
            response.text,
            request_body,
        )
        raise
    is_created = response.status_code == Config.HttpStatus.CREATED
    logger.info(
        "식단 upstream 등록 완료: restaurant_id=%s, meal_type=%s, "
        "created=%s, status_code=%s",
        restaurant_id,
        meal_type.value,
        is_created,
        response.status_code,
    )
    return is_created


async def post_restaurant_manager_application(
    restaurant_id: int,
    client: XUserIDClient,
) -> int | None:
    """식당 manager 등록 신청을 생성합니다."""
    response = await client.post(
        f"{Config.MEAL_SERVICE_URL}/restaurants/{restaurant_id}/manager-requests"
    )
    response.raise_for_status()
    data = response.json().get("data", {})
    request_id = data.get("request_id") if isinstance(data, dict) else None
    return request_id if isinstance(request_id, int) else None
