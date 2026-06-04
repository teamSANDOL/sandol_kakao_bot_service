from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Literal

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.config import Config
from app.routers import meal as meal_router_module
from app.routers.meal import meal_router
from app.schemas.meals import MealResponse, MealType, RestaurantResponse
from app.utils.http import get_async_client
from app.utils.kakao import parse_payload


def make_payload() -> SimpleNamespace:
    return SimpleNamespace(
        user_request=SimpleNamespace(user=SimpleNamespace(id="kakao-user-1")),
        action=SimpleNamespace(detail_params={}),
    )


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(meal_router)

    async def fake_parse_payload() -> SimpleNamespace:
        return make_payload()

    async def fake_get_async_client():
        yield None

    app.dependency_overrides[parse_payload] = fake_parse_payload
    app.dependency_overrides[get_async_client] = fake_get_async_client

    return TestClient(app)


def _meal_response(
    *,
    meal_id: int,
    restaurant_id: int,
    restaurant_name: str,
    registered_at: datetime,
) -> MealResponse:
    return MealResponse(
        id=meal_id,
        menu=[restaurant_name],
        meal_type=MealType.lunch,
        restaurant_id=restaurant_id,
        restaurant_name=restaurant_name,
        registered_at=registered_at,
        updated_at=registered_at,
    )


def _restaurant_response(
    *,
    restaurant_id: int,
    name: str,
    establishment_type: Literal["student", "fixed_menu_restaurant", "fixed_korean_buffet", "variable_korean_buffet"],
) -> RestaurantResponse:
    return RestaurantResponse(
        id=restaurant_id,
        name=name,
        establishment_type=establishment_type,
    )


def test_meal_view_orders_today_first_and_pushes_student_cafeterias_last(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(tz=Config.TZ).replace(hour=12, minute=0, second=0, microsecond=0)
    yesterday = now - timedelta(days=1)
    two_days_ago = now - timedelta(days=2)

    async def fake_fetch_latest_meals(*_: object):
        return [
            _meal_response(
                meal_id=1,
                restaurant_id=1,
                restaurant_name="E동 레스토랑",
                registered_at=now.replace(hour=10),
            ),
            _meal_response(
                meal_id=2,
                restaurant_id=2,
                restaurant_name="외부식당B",
                registered_at=yesterday.replace(hour=23),
            ),
            _meal_response(
                meal_id=3,
                restaurant_id=3,
                restaurant_name="일반식당A",
                registered_at=now.replace(hour=9),
            ),
            _meal_response(
                meal_id=4,
                restaurant_id=4,
                restaurant_name="TIP 가가식당",
                registered_at=now.replace(hour=8),
            ),
            _meal_response(
                meal_id=5,
                restaurant_id=5,
                restaurant_name="일반식당C",
                registered_at=now.replace(hour=11),
            ),
            _meal_response(
                meal_id=6,
                restaurant_id=6,
                restaurant_name="외부식당D",
                registered_at=two_days_ago.replace(hour=12),
            ),
        ]

    async def fake_fetch_restaurants(*_: object, **__: object):
        return [
            _restaurant_response(
                restaurant_id=1,
                name="E동 레스토랑",
                establishment_type="student",
            ),
            _restaurant_response(
                restaurant_id=2,
                name="외부식당B",
                establishment_type="fixed_menu_restaurant",
            ),
            _restaurant_response(
                restaurant_id=3,
                name="일반식당A",
                establishment_type="fixed_menu_restaurant",
            ),
            _restaurant_response(
                restaurant_id=4,
                name="TIP 가가식당",
                establishment_type="student",
            ),
            _restaurant_response(
                restaurant_id=5,
                name="일반식당C",
                establishment_type="fixed_korean_buffet",
            ),
            _restaurant_response(
                restaurant_id=6,
                name="외부식당D",
                establishment_type="fixed_menu_restaurant",
            ),
        ]

    monkeypatch.setattr(
        meal_router_module,
        "fetch_latest_meals",
        fake_fetch_latest_meals,
    )
    monkeypatch.setattr(
        meal_router_module,
        "fetch_restaurants",
        fake_fetch_restaurants,
    )

    response = client.post("/meal/view", json={})

    assert response.status_code == 200
    body = str(response.json())

    ordered_titles = [
        "일반식당A(점심)",
        "일반식당C(점심)",
        "TIP 가가식당(점심)",
        "E동 레스토랑(점심)",
        "외부식당B(점심)",
        "외부식당D(점심)",
    ]
    title_positions = [body.index(title) for title in ordered_titles]

    assert title_positions == sorted(title_positions)


def test_meal_view_skips_student_restaurant_lookup_for_specific_restaurant(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(tz=Config.TZ).replace(hour=12, minute=0, second=0, microsecond=0)

    async def fake_parse_payload() -> SimpleNamespace:
        return SimpleNamespace(
            user_request=SimpleNamespace(user=SimpleNamespace(id="kakao-user-1")),
            action=SimpleNamespace(
                detail_params={
                    "Cafeteria": SimpleNamespace(value="TIP 가가식당"),
                }
            ),
        )

    async def fake_fetch_latest_meals(*_: object):
        return [
            _meal_response(
                meal_id=1,
                restaurant_id=4,
                restaurant_name="TIP 가가식당",
                registered_at=now.replace(hour=8),
            ),
            MealResponse(
                id=2,
                menu=["저녁"],
                meal_type=MealType.dinner,
                restaurant_id=4,
                restaurant_name="TIP 가가식당",
                registered_at=now.replace(hour=9),
                updated_at=now.replace(hour=9),
            ),
        ]

    async def fail_fetch_restaurants(*_: object, **__: object):
        raise AssertionError("fetch_restaurants should not be called")

    client.app.dependency_overrides[parse_payload] = fake_parse_payload
    monkeypatch.setattr(
        meal_router_module,
        "fetch_latest_meals",
        fake_fetch_latest_meals,
    )
    monkeypatch.setattr(
        meal_router_module,
        "fetch_restaurants",
        fail_fetch_restaurants,
    )

    response = client.post("/meal/view", json={})

    assert response.status_code == 200
