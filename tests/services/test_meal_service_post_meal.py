"""Tests for the meal-service registration request contract."""

from datetime import datetime

import pytest

from app.config import Config
from app.schemas.meals import MealType
from app.services.meal_service import post_meal


class FakeResponse:
    """Small HTTP response double used by the service unit test."""

    status_code = 201
    text = "{}"

    def raise_for_status(self) -> None:
        """Match the httpx response API."""


class FakeClient:
    """Capture the JSON body sent by post_meal."""

    def __init__(self) -> None:
        self.body: dict[str, object] | None = None

    async def post(self, url: str, *, json: dict[str, object]) -> FakeResponse:
        """Capture the request and return a created response."""
        del url
        self.body = json
        return FakeResponse()


@pytest.mark.asyncio
async def test_post_meal_sends_today_as_date() -> None:
    """The default registration date is today's KST date."""
    client = FakeClient()
    created = await post_meal(MealType.lunch, [" 김치찌개 "], 1, client)

    assert created is True
    assert client.body is not None
    assert client.body["date"] == datetime.now(Config.TZ).date().isoformat()
    assert client.body["menu"] == ["김치찌개"]
