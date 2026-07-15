import json
from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from kakao_chatbot.context import Context, ContextParam
import pytest

from app.routers import meal as meal_router_module
from app.routers.meal import meal_router
from app.schemas.meals import MealResponse, MealType, RestaurantResponse
from app.services.user_service import get_current_user, get_xuser_client_by_payload
from app.utils.kakao import parse_payload
from app.utils.meal import select_restaurant


def make_menu_context(name: str, restaurant_name: str, menu: list[str]) -> Context:
    menu_value = json.dumps(menu, ensure_ascii=False)
    return Context(
        name=name,
        params={
            "menu_list": ContextParam(menu_value, menu_value),
            "restaurant_name": ContextParam(restaurant_name, restaurant_name),
        },
        lifespan=5,
        ttl=300,
    )


def make_meal_response(meal_type: MealType, menu: list[str]) -> MealResponse:
    now = datetime.now(timezone.utc)
    return MealResponse(
        id=1 if meal_type == MealType.lunch else 2,
        menu=menu,
        meal_type=meal_type,
        restaurant_name="산돌식당",
        restaurant_id=10,
        registered_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_meal_submit_posts_only_existing_meal_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    posted_meals: list[tuple[MealType, list[str], int]] = []

    async def fake_post_meal(
        meal_type: MealType,
        menu: list[str],
        restaurant_id: int,
        client: object,
    ) -> bool:
        posted_meals.append((meal_type, menu, restaurant_id))
        return True

    async def fake_fetch_latest_meals(
        client: object,
        restaurant_id: int,
    ) -> list[MealResponse]:
        return [
            make_meal_response(MealType.lunch, ["김치찌개"]),
            make_meal_response(MealType.dinner, ["돈까스"]),
        ]

    monkeypatch.setattr(meal_router_module, "post_meal", fake_post_meal)
    monkeypatch.setattr(
        meal_router_module,
        "fetch_latest_meals",
        fake_fetch_latest_meals,
    )

    payload = SimpleNamespace(
        user_id="kakao-user-1",
        contexts=[make_menu_context("lunch_menu", "산돌식당", ["김치찌개"])],
    )
    restaurant = RestaurantResponse(id=10, name="산돌식당", establishment_type="student")
    app = FastAPI()
    app.include_router(meal_router)

    async def fake_parse_payload() -> SimpleNamespace:
        return payload

    async def fake_get_current_user() -> SimpleNamespace:
        return SimpleNamespace()

    async def fake_get_xuser_client_by_payload() -> object:
        return object()

    async def fake_select_restaurant() -> RestaurantResponse:
        return restaurant

    app.dependency_overrides[parse_payload] = fake_parse_payload
    app.dependency_overrides[get_current_user] = fake_get_current_user
    app.dependency_overrides[get_xuser_client_by_payload] = fake_get_xuser_client_by_payload
    app.dependency_overrides[select_restaurant] = fake_select_restaurant

    response = TestClient(app).post("/meal/submit", json={})

    assert response.status_code == 200
    assert posted_meals == [(MealType.lunch, ["김치찌개"], 10)]
