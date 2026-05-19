from types import SimpleNamespace
from typing import cast

import pytest
from httpx import HTTPStatusError, Request, Response
from httpx import AsyncClient
from kakao_chatbot import Payload

from app.config import Config
from app.services.auth_service import generate_login_link
from app.utils.kakao import KakaoError


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
        cast(Payload, cast(object, SimpleNamespace(user_id="kakao-user-1"))),
        cast(AsyncClient, cast(object, client)),
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

    await generate_login_link(
        cast(Payload, cast(object, SimpleNamespace(user_id="kakao-user-1"))),
        cast(AsyncClient, cast(object, client)),
    )

    assert client.calls[0][1]["redirect_after"] is None


@pytest.mark.asyncio
async def test_generate_login_link_returns_kakao_error_for_invalid_callback_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        Config,
        "LOGIN_CALLBACK_URL",
        "not-a-valid-url",
    )
    monkeypatch.setattr(Config, "LOGIN_REDIRECT_AFTER", None)
    monkeypatch.setattr(Config, "AUTH_RELAY_URL", "http://auth-relay:8000/relay")
    monkeypatch.setattr(Config, "KC_CLIENT_ID", "sandol-kakao-bot")

    client = _RecordingAsyncClient()

    with pytest.raises(KakaoError, match="로그인 링크를 준비하는 중 오류가 발생했습니다"):
        await generate_login_link(
            cast(Payload, cast(object, SimpleNamespace(user_id="kakao-user-1"))),
            cast(AsyncClient, cast(object, client)),
        )


class _FailingAsyncClient:
    async def post(self, url: str, json: dict[str, object]) -> _FakeResponse:
        request = Request("POST", url)
        response = Response(502, request=request, text="bad gateway")
        raise HTTPStatusError("relay failed", request=request, response=response)


@pytest.mark.asyncio
async def test_generate_login_link_returns_kakao_error_when_relay_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        Config,
        "LOGIN_CALLBACK_URL",
        "https://sandol.house.sio2.kr/kakao-bot/users/callback",
    )
    monkeypatch.setattr(Config, "LOGIN_REDIRECT_AFTER", None)
    monkeypatch.setattr(Config, "AUTH_RELAY_URL", "http://auth-relay:8000/relay")
    monkeypatch.setattr(Config, "KC_CLIENT_ID", "sandol-kakao-bot")

    with pytest.raises(KakaoError, match="로그인 링크를 생성하지 못했습니다"):
        await generate_login_link(
            cast(Payload, cast(object, SimpleNamespace(user_id="kakao-user-1"))),
            cast(AsyncClient, cast(object, _FailingAsyncClient())),
        )
