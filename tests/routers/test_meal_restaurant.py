import json
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response
import pytest

from app.config import Config
from app.routers import meal as meal_router_module
from app.routers.meal import meal_router
from app.schemas.meals import Location, RestaurantResponse
from app.utils.http import get_async_client
from app.utils.kakao import parse_payload


def make_payload() -> SimpleNamespace:
    return SimpleNamespace(
        user_id="kakao-user-1",
        action=SimpleNamespace(client_extra={"restaurant_name": "산돌식당"}),
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


def _serialized_response(response: Response) -> str:
    return json.dumps(response.json(), ensure_ascii=False)


def test_meal_restaurant_shows_price_and_building_for_on_campus(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_fetch_restaurant_by_name(*_: object):
        return RestaurantResponse(
            id=1,
            name="산돌식당",
            establishment_type="student",
            price=7000,
            location=Location(
                is_campus=True,
                building="TIP",
                map_links={"kakao": "https://example.com/map"},
            ),
        )

    monkeypatch.setattr(
        meal_router_module,
        "fetch_restaurant_by_name",
        fake_fetch_restaurant_by_name,
    )

    response = client.post("/meal/restaurant", json={})

    body = _serialized_response(response)
    assert response.status_code == 200
    assert "1인분 가격" in body
    assert "7000원" in body
    assert '"위치"' in body
    assert "TIP" in body
    assert "분류" not in body


def test_meal_restaurant_shows_off_campus_label(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_fetch_restaurant_by_name(*_: object):
        return RestaurantResponse(
            id=2,
            name="교외식당",
            establishment_type="fixed_menu_restaurant",
            price=8000,
            location=Location(
                is_campus=False,
                building="외부건물",
                map_links={"naver": "https://example.com/map"},
            ),
        )

    monkeypatch.setattr(
        meal_router_module,
        "fetch_restaurant_by_name",
        fake_fetch_restaurant_by_name,
    )

    response = client.post("/meal/restaurant", json={})

    body = _serialized_response(response)
    assert response.status_code == 200
    assert "1인분 가격" in body
    assert "8000원" in body
    assert '"위치"' in body
    assert "교외" in body
    assert "분류" not in body


def _patch_fetch(
    monkeypatch: pytest.MonkeyPatch, restaurant: RestaurantResponse
) -> None:
    async def fake_fetch_restaurant_by_name(*_: object):
        return restaurant

    monkeypatch.setattr(
        meal_router_module,
        "fetch_restaurant_by_name",
        fake_fetch_restaurant_by_name,
    )


def test_student_cafeteria_shows_weekly_menu_button(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_fetch(
        monkeypatch,
        RestaurantResponse(
            id=1,
            name="TIP 가가식당",
            establishment_type="student",
            price=6000,
            location=Location(
                is_campus=True,
                building="TIP",
                map_links={"kakao": "https://kko.kakao.com/qUpUMrAKti"},
            ),
        ),
    )

    response = client.post("/meal/restaurant", json={})

    body = _serialized_response(response)
    assert response.status_code == 200
    assert "주간 식단표 보기" in body
    assert Config.WEEKLY_MENU_URL in body
    assert '"buttonLayout": "vertical"' in body


def test_owner_restaurant_hides_weekly_menu_button(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_fetch(
        monkeypatch,
        RestaurantResponse(
            id=2,
            name="미가식당",
            establishment_type="fixed_menu_restaurant",
            price=8000,
            location=Location(
                is_campus=False,
                building="외부건물",
                map_links={"naver": "https://example.com/map"},
            ),
        ),
    )

    response = client.post("/meal/restaurant", json={})

    body = _serialized_response(response)
    assert response.status_code == 200
    assert "주간 식단표 보기" not in body
    assert Config.WEEKLY_MENU_URL not in body
    assert "buttonLayout" not in body
