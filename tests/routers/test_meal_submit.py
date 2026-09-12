import json
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from kakao_chatbot.context import Context, ContextParam
import pytest

from app.config import Config
from app.config.blocks import CAFETERIA_REGISTER_QUICK_REPLIES
from app.routers import meal as meal_router_module
from app.routers.meal import meal_router
from app.schemas.meals import MealResponse, MealType, RestaurantResponse
from app.services.user_service import get_current_user, get_xuser_client_by_payload
from app.utils.kakao import parse_payload
from app.utils.meal import select_restaurant


def make_menu_context(
    name: str,
    restaurant_name: str,
    menu: list[str],
    served_date: date | None = None,
) -> Context:
    menu_value = json.dumps(menu, ensure_ascii=False)
    return Context(
        name=name,
        params={
            "menu_list": ContextParam(menu_value, menu_value),
            "restaurant_name": ContextParam(restaurant_name, restaurant_name),
            **(
                {
                    "served_date": ContextParam(
                        served_date.isoformat(), served_date.isoformat()
                    )
                }
                if served_date is not None
                else {}
            ),
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
        served_date=date.today(),
    )


class FakeResponse:
    """Meal service response used by the submission route test."""

    status_code = 201
    text = "{}"

    def raise_for_status(self) -> None:
        """Match the httpx response API."""


class CapturingClient:
    """Capture the registration request from the production submit path."""

    def __init__(self) -> None:
        self.posts: list[tuple[str, dict[str, object]]] = []

    async def post(
        self,
        url: str,
        *,
        json: dict[str, object],
    ) -> FakeResponse:
        """Record the request and return a created response."""
        self.posts.append((url, json))
        return FakeResponse()


@pytest.mark.asyncio
async def test_meal_submit_registers_today_in_kst(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = CapturingClient()

    async def fake_fetch_latest_meals(
        client: object,
        restaurant_id: int,
    ) -> list[MealResponse]:
        return [
            make_meal_response(MealType.lunch, ["김치찌개"]),
            make_meal_response(MealType.dinner, ["돈까스"]),
        ]

    monkeypatch.setattr(
        meal_router_module,
        "fetch_latest_meals",
        fake_fetch_latest_meals,
    )

    payload = SimpleNamespace(
        user_id="kakao-user-1",
        contexts=[
            make_menu_context(
                "lunch_menu",
                "산돌식당",
                ["김치찌개"],
                datetime.now(Config.TZ).date() + timedelta(days=1),
            )
        ],
    )
    restaurant = RestaurantResponse(
        id=10, name="산돌식당", establishment_type="student"
    )
    app = FastAPI()
    app.include_router(meal_router)

    async def fake_parse_payload() -> SimpleNamespace:
        return payload

    async def fake_get_current_user() -> SimpleNamespace:
        return SimpleNamespace()

    async def fake_get_xuser_client_by_payload() -> CapturingClient:
        return client

    async def fake_select_restaurant() -> RestaurantResponse:
        return restaurant

    app.dependency_overrides[parse_payload] = fake_parse_payload
    app.dependency_overrides[get_current_user] = fake_get_current_user
    app.dependency_overrides[get_xuser_client_by_payload] = (
        fake_get_xuser_client_by_payload
    )
    app.dependency_overrides[select_restaurant] = fake_select_restaurant

    response = TestClient(app).post("/meal/submit", json={})

    assert response.status_code == 200
    assert client.posts == [
        (
            f"{Config.MEAL_SERVICE_URL}/meals/10",
            {
                "meal_type": MealType.lunch,
                "menu": ["김치찌개"],
                "date": datetime.now(Config.TZ).date().isoformat(),
            },
        )
    ]
    context_values = response.json()["context"]["values"]
    assert "served_date" not in context_values[0]["params"]


def test_date_selection_route_and_quick_reply_are_not_exposed() -> None:
    assert "/register/date" not in {route.path for route in meal_router.routes}
    assert all(
        quick_reply.label != "메뉴 제공일 변경"
        for quick_reply in CAFETERIA_REGISTER_QUICK_REPLIES
    )
