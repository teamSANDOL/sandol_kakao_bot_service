import json
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import ConnectError, Response
import pytest

from app.config import BlockID, Config
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
    assert BlockID.WEEKLY_MENU.value in body
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
    assert BlockID.WEEKLY_MENU.value not in body
    assert "buttonLayout" not in body


def test_weekly_menu_returns_simple_images(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_fetch_weekly_menu_img_links(*_: object) -> list[str]:
        return ["https://img/tip.jpg", "https://img/e.jpg"]

    monkeypatch.setattr(
        meal_router_module,
        "fetch_weekly_menu_img_links",
        fake_fetch_weekly_menu_img_links,
    )

    response = client.post("/meal/weekly_menu", json={})

    assert response.status_code == 200
    outputs = response.json()["template"]["outputs"]
    assert len(outputs) == 3
    assert [output["simpleImage"]["imageUrl"] for output in outputs[:2]] == [
        "https://img/tip.jpg",
        "https://img/e.jpg",
    ]
    assert outputs[0]["simpleImage"]["altText"] == "주간 식단표 정보 사진"
    link_button = outputs[2]["textCard"]["buttons"][0]
    assert link_button["label"] == "웹사이트에서 확인하기"
    assert link_button["webLinkUrl"] == Config.WEEKLY_MENU_URL


def test_weekly_menu_falls_back_to_link_card_when_static_info_fails(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_fetch_weekly_menu_img_links(*_: object) -> list[str]:
        raise ConnectError("static-info down")

    monkeypatch.setattr(
        meal_router_module,
        "fetch_weekly_menu_img_links",
        fake_fetch_weekly_menu_img_links,
    )

    response = client.post("/meal/weekly_menu", json={})

    assert response.status_code == 200
    outputs = response.json()["template"]["outputs"]
    assert len(outputs) == 1
    assert "불러오지 못했습니다" in outputs[0]["textCard"]["description"]
    assert outputs[0]["textCard"]["buttons"][0]["webLinkUrl"] == Config.WEEKLY_MENU_URL


def test_weekly_menu_without_images_returns_notice(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_fetch_weekly_menu_img_links(*_: object) -> list[str]:
        return []

    monkeypatch.setattr(
        meal_router_module,
        "fetch_weekly_menu_img_links",
        fake_fetch_weekly_menu_img_links,
    )

    response = client.post("/meal/weekly_menu", json={})

    assert response.status_code == 200
    outputs = response.json()["template"]["outputs"]
    assert len(outputs) == 1
    assert "불러오지 못했습니다" in outputs[0]["textCard"]["description"]
