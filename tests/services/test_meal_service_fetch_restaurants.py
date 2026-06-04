from types import SimpleNamespace

import pytest

from app.services.meal_service import fetch_restaurants


class FakeClient:
    def __init__(self) -> None:
        self.request_url: str | None = None
        self.request_params: dict[str, str | int] | None = None

    async def get(self, url: str, params: dict[str, str | int] | None = None) -> SimpleNamespace:
        self.request_url = url
        self.request_params = params

        def raise_for_status() -> None:
            return None

        def json() -> dict[str, list[dict[str, object]]]:
            return {
                "data": [
                    {
                        "id": 1,
                        "name": "TIP 가가식당",
                        "establishment_type": "student",
                        "price": None,
                        "location": None,
                        "opening_time": None,
                        "break_time": None,
                        "breakfast_time": None,
                        "brunch_time": None,
                        "lunch_time": None,
                        "dinner_time": None,
                        "owner": None,
                    }
                ]
            }

        return SimpleNamespace(raise_for_status=raise_for_status, json=json)


@pytest.mark.asyncio
async def test_fetch_restaurants_uses_trailing_slash_for_collection_endpoint() -> None:
    client = FakeClient()

    await fetch_restaurants(client, establishment_type="student")

    assert client.request_url is not None
    assert client.request_url.endswith("/restaurants/")
    assert client.request_params == {
        "size": 100,
        "establishment_type": "student",
    }
