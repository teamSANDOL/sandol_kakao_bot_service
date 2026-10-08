import pytest

from app.config import Config
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


@pytest.mark.asyncio
async def test_get_async_client_uses_downstream_timeout() -> None:
    async for client in get_async_client():
        assert client.timeout.connect == 1.0
        assert client.timeout.read == 3.0
        assert client.timeout.write == 3.0
        assert client.timeout.pool == 3.0


@pytest.mark.asyncio
async def test_xuser_client_uses_downstream_timeout() -> None:
    async with XUserIDClient(user_id="user-1") as client:
        assert client.timeout.connect == 1.0
        assert client.timeout.read == 3.0
        assert client.timeout.write == 3.0
        assert client.timeout.pool == 3.0


@pytest.mark.asyncio
@pytest.mark.parametrize("timeout", [0.5, None])
async def test_xuser_client_respects_timeout_override(timeout: float | None) -> None:
    async with XUserIDClient(user_id="user-1", timeout=timeout) as client:
        assert client.timeout.connect == timeout
        assert client.timeout.read == timeout
        assert client.timeout.write == timeout
        assert client.timeout.pool == timeout


@pytest.mark.asyncio
async def test_clients_use_configured_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Config, "DOWNSTREAM_HTTP_TIMEOUT_SECONDS", 0.8)
    monkeypatch.setattr(Config, "DOWNSTREAM_HTTP_CONNECT_TIMEOUT_SECONDS", 0.2)

    async for client in get_async_client():
        assert client.timeout.connect == 0.2
        assert client.timeout.read == 0.8
        assert client.timeout.write == 0.8
        assert client.timeout.pool == 0.8
    async with XUserIDClient(user_id="user-1") as client:
        assert client.timeout.connect == 0.2
        assert client.timeout.read == 0.8
        assert client.timeout.write == 0.8
        assert client.timeout.pool == 0.8
