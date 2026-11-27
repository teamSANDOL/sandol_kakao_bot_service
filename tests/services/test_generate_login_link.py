import base64
import hashlib
import hmac
import json
from types import SimpleNamespace
from typing import cast

import pytest
from httpx import ConnectError, HTTPStatusError, Request, Response
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
        self.raw: list[tuple[bytes, dict[str, str]]] = []

    async def post(
        self, url: str, content: bytes, headers: dict[str, str]
    ) -> _FakeResponse:
        self.calls.append((url, json.loads(content)))
        self.raw.append((content, headers))
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
    async def post(
        self, url: str, content: bytes, headers: dict[str, str]
    ) -> _FakeResponse:
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


def _relay_verify(secret: str, path: str, body: bytes, headers: dict[str, str]) -> bool:
    """auth-relay README 규약대로 독립 구현한 검증기."""
    canonical = "\n".join(
        [
            "SANDOL-RELAY-HMAC-V1",
            "POST",
            path,
            headers["X-Relay-Timestamp"],
            headers["X-Relay-Nonce"],
            headers["X-Relay-Client-Key"],
            hashlib.sha256(body).hexdigest(),
        ]
    )
    mac = hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).digest()
    expected = base64.urlsafe_b64encode(mac).decode().rstrip("=")
    return hmac.compare_digest(expected, headers["X-Relay-Request-Signature"])


@pytest.mark.asyncio
async def test_generate_login_link_signs_request_for_public_https_relay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        Config, "LOGIN_CALLBACK_URL", "https://example.com/kakao-bot/users/callback"
    )
    monkeypatch.setattr(Config, "LOGIN_REDIRECT_AFTER", None)
    monkeypatch.setattr(Config, "AUTH_RELAY_URL", "https://auth.example.com/relay")
    monkeypatch.setattr(Config, "KC_CLIENT_ID", "sandol-kakao-bot")
    monkeypatch.setattr(Config, "RELAY_ISSUE_LINK_SECRET", "issue-secret")

    client = _RecordingAsyncClient()
    await generate_login_link(
        cast(Payload, cast(object, SimpleNamespace(user_id="kakao-user-1"))),
        cast(AsyncClient, cast(object, client)),
    )
    await generate_login_link(
        cast(Payload, cast(object, SimpleNamespace(user_id="kakao-user-1"))),
        cast(AsyncClient, cast(object, client)),
    )

    assert client.calls[0][0] == "https://auth.example.com/relay/issue_login_link"
    body, headers = client.raw[0]
    assert headers["X-Relay-Client-Key"] == "sandol-kakao-bot"
    assert _relay_verify("issue-secret", "/issue_login_link", body, headers)
    assert not _relay_verify("other-secret", "/issue_login_link", body, headers)
    assert not _relay_verify("issue-secret", "/issue_login_link", body + b" ", headers)
    # 요청마다 nonce가 달라야 relay의 재전송 거부에 걸리지 않는다.
    assert headers["X-Relay-Nonce"] != client.raw[1][1]["X-Relay-Nonce"]


class _NetworkErrorAsyncClient:
    async def post(
        self, url: str, content: bytes, headers: dict[str, str]
    ) -> _FakeResponse:
        raise ConnectError("tls failed", request=Request("POST", url))


@pytest.mark.asyncio
async def test_generate_login_link_returns_kakao_error_on_network_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        Config, "LOGIN_CALLBACK_URL", "https://example.com/kakao-bot/users/callback"
    )
    monkeypatch.setattr(Config, "LOGIN_REDIRECT_AFTER", None)
    monkeypatch.setattr(Config, "AUTH_RELAY_URL", "https://auth.example.com/relay")

    with pytest.raises(KakaoError, match="로그인 링크를 생성하지 못했습니다"):
        await generate_login_link(
            cast(Payload, cast(object, SimpleNamespace(user_id="kakao-user-1"))),
            cast(AsyncClient, cast(object, _NetworkErrorAsyncClient())),
        )


@pytest.mark.asyncio
async def test_generate_login_link_sends_unsigned_when_secret_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        Config, "LOGIN_CALLBACK_URL", "https://example.com/kakao-bot/users/callback"
    )
    monkeypatch.setattr(Config, "LOGIN_REDIRECT_AFTER", None)
    monkeypatch.setattr(Config, "AUTH_RELAY_URL", "http://auth-relay:8000/relay")
    monkeypatch.setattr(Config, "RELAY_ISSUE_LINK_SECRET", "")

    client = _RecordingAsyncClient()
    await generate_login_link(
        cast(Payload, cast(object, SimpleNamespace(user_id="kakao-user-1"))),
        cast(AsyncClient, cast(object, client)),
    )

    _, headers = client.raw[0]
    assert headers == {"Content-Type": "application/json"}
