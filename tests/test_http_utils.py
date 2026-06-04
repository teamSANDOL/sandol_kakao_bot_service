import pytest

from app.utils.http import XUserIDClient, get_async_client


@pytest.mark.asyncio
async def test_get_async_client_enables_follow_redirects() -> None:
    async for client in get_async_client():
        assert client.follow_redirects is True


@pytest.mark.asyncio
async def test_xuser_client_enables_follow_redirects_by_default() -> None:
    client = XUserIDClient(user_id="user-1")
    try:
        assert client.follow_redirects is True
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_xuser_client_respects_explicit_follow_redirects_override() -> None:
    client = XUserIDClient(user_id="user-1", follow_redirects=False)
    try:
        assert client.follow_redirects is False
    finally:
        await client.aclose()
