from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.config import Config
from app.services.auth_service import generate_login_link


class _FakeResponse:
    def raise_for_status(self) -> None:
        """Return a successful response."""

    def json(self) -> dict[str, object]:
        """Return a valid auth-relay response payload."""
        return {
            "login_link": "https://relay.example.com/login/token",
            "expires_in": 300,
        }


class _RecordingAsyncClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def post(self, url: str, json: dict[str, object]) -> _FakeResponse:
        self.calls.append((url, json))
        return _FakeResponse()


@pytest.mark.asyncio
async def test_generate_login_link_accepts_relative_redirect_after(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        Config,
        "LOGIN_CALLBACK_URL",
        "https://sandol.house.sio2.kr/kakao-bot/users/callback",
    )
    monkeypatch.setattr(
        Config, "LOGIN_REDIRECT_AFTER", "/auth/realms/Sandori/account/"
    )
    monkeypatch.setattr(Config, "AUTH_RELAY_URL", "http://auth-relay:8000/relay")
    monkeypatch.setattr(Config, "KC_CLIENT_ID", "sandol-kakao-bot")

    client = _RecordingAsyncClient()

    response = await generate_login_link(
        SimpleNamespace(user_id="kakao-user-1"), client
    )

    assert response.login_link == "https://relay.example.com/login/token"
    assert client.calls == [
        (
            "http://auth-relay:8000/relay/issue_login_link",
            {
                "chatbot_user_id": "kakao-user-1",
                "callback_url": "https://sandol.house.sio2.kr/kakao-bot/users/callback",
                "client_key": "sandol-kakao-bot",
                "redirect_after": "/auth/realms/Sandori/account/",
            },
        )
    ]


@pytest.mark.asyncio
async def test_generate_login_link_treats_blank_redirect_after_as_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        Config,
        "LOGIN_CALLBACK_URL",
        "https://sandol.house.sio2.kr/kakao-bot/users/callback",
    )
    monkeypatch.setattr(Config, "LOGIN_REDIRECT_AFTER", "")
    monkeypatch.setattr(Config, "AUTH_RELAY_URL", "http://auth-relay:8000/relay")
    monkeypatch.setattr(Config, "KC_CLIENT_ID", "sandol-kakao-bot")

    client = _RecordingAsyncClient()

    await generate_login_link(SimpleNamespace(user_id="kakao-user-1"), client)

    assert client.calls[0][1]["redirect_after"] is None


@pytest.mark.asyncio
async def test_generate_login_link_rejects_absolute_redirect_after(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        Config,
        "LOGIN_CALLBACK_URL",
        "https://sandol.house.sio2.kr/kakao-bot/users/callback",
    )
    monkeypatch.setattr(
        Config,
        "LOGIN_REDIRECT_AFTER",
        "https://sandol.house.sio2.kr/auth/realms/Sandori/account/",
    )
    monkeypatch.setattr(Config, "AUTH_RELAY_URL", "http://auth-relay:8000/relay")
    monkeypatch.setattr(Config, "KC_CLIENT_ID", "sandol-kakao-bot")

    client = _RecordingAsyncClient()

    with pytest.raises(ValidationError, match="safe relative path"):
        await generate_login_link(SimpleNamespace(user_id="kakao-user-1"), client)
