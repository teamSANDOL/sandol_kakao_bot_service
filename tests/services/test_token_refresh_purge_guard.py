"""Keycloak 토큰 갱신 실패 시 저장 토큰 삭제 조건(invalid_grant 한정) 테스트."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import cast

from fastapi import HTTPException
from keycloak.exceptions import KeycloakPostError
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Config
from app.models.users import User
from app.services import auth_service, user_service
from app.utils.kakao import KakaoError, LoginRequiredError
from app.utils.security import encrypt_token


def _install_failing_client(monkeypatch: pytest.MonkeyPatch, error: Exception) -> None:
    async def fake_a_refresh_token(_: str) -> dict[str, object]:
        raise error

    kc = SimpleNamespace(a_refresh_token=fake_a_refresh_token)
    monkeypatch.setattr(auth_service, "get_keycloak_client", lambda: kc)


@pytest.mark.asyncio
async def test_invalid_grant_maps_to_unauthorized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = KeycloakPostError(
        error_message="x",
        response_code=400,
        response_body=b'{"error":"invalid_grant","error_description":"Session not active"}',
    )
    _install_failing_client(monkeypatch, error)

    with pytest.raises(HTTPException) as exc_info:
        await auth_service.request_token_refresh("rt")

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        b'{"error":"invalid_client"}',
        b'{"error":"unauthorized_client"}',
        b'{"error":"invalid_request"}',
        b"<html>bad gateway</html>",
        b"",
        b"[]",
    ],
)
async def test_other_400_is_not_terminal(
    monkeypatch: pytest.MonkeyPatch, body: bytes
) -> None:
    error = KeycloakPostError(error_message="x", response_code=400, response_body=body)
    _install_failing_client(monkeypatch, error)

    with pytest.raises(HTTPException) as exc_info:
        await auth_service.request_token_refresh("rt")

    assert exc_info.value.status_code != 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        KeycloakPostError(error_message="x", response_code=503, response_body=b""),
        TimeoutError("timeout"),
        ConnectionError("down"),
    ],
)
async def test_server_and_network_errors_are_not_terminal(
    monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    _install_failing_client(monkeypatch, error)

    with pytest.raises(HTTPException) as exc_info:
        await auth_service.request_token_refresh("rt")

    assert exc_info.value.status_code != 401


class _DummyDB:
    def __init__(self) -> None:
        self.executed: list[object] = []

    async def execute(self, statement: object) -> SimpleNamespace:
        self.executed.append(statement)
        return SimpleNamespace(rowcount=1)

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


def _make_user() -> SimpleNamespace:
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=1,
        keycloak_id="keycloak-sub-1",
        access_token=encrypt_token("access-token"),
        refresh_token=encrypt_token("refresh-token"),
        access_token_expires_at=now + timedelta(minutes=5),
        refresh_token_expires_at=now + timedelta(days=30),
    )


async def _refresh_raising(
    monkeypatch: pytest.MonkeyPatch, status_code: int
) -> _DummyDB:
    async def fake(*_: object, **__: object) -> dict[str, object]:
        raise HTTPException(status_code=status_code, detail="x")

    monkeypatch.setattr(user_service, "request_token_refresh", fake)
    db = _DummyDB()
    expected = LoginRequiredError if status_code == 401 else KakaoError
    with pytest.raises(expected):
        await user_service._perform_token_refresh(
            cast(User, _make_user()), cast(AsyncSession, cast(object, db))
        )
    return db


@pytest.mark.asyncio
async def test_purge_disabled_keeps_tokens_but_asks_relogin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(Config, "KC_TOKEN_PURGE_ENABLED", False)

    db = await _refresh_raising(monkeypatch, 401)

    assert db.executed == []


@pytest.mark.asyncio
async def test_purge_enabled_clears_tokens_on_invalid_grant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(Config, "KC_TOKEN_PURGE_ENABLED", True)

    db = await _refresh_raising(monkeypatch, 401)

    assert len(db.executed) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [500, 503])
async def test_transient_failure_returns_retry_message_without_purge(
    monkeypatch: pytest.MonkeyPatch, status_code: int
) -> None:
    db = await _refresh_raising(monkeypatch, status_code)

    assert db.executed == []


def _remote_session_user() -> User:
    return cast(User, _make_user())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "expected_active"),
    [(401, False), (503, True), (500, True)],
)
async def test_remote_session_check_only_stale_on_unauthorized(
    monkeypatch: pytest.MonkeyPatch, status_code: int, expected_active: bool
) -> None:
    async def fake(*_: object, **__: object) -> dict[str, object]:
        raise HTTPException(status_code=status_code, detail="x")

    monkeypatch.setattr(auth_service, "request_token_refresh", fake)

    result = await auth_service._has_active_remote_login_session(_remote_session_user())

    assert result is expected_active


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("body", "expected_active"),
    [(b'{"error":"invalid_client"}', True), (b'{"error":"invalid_grant"}', False)],
)
async def test_remote_session_check_by_oauth_error_code(
    monkeypatch: pytest.MonkeyPatch, body: bytes, expected_active: bool
) -> None:
    error = KeycloakPostError(error_message="x", response_code=400, response_body=body)
    _install_failing_client(monkeypatch, error)

    result = await auth_service._has_active_remote_login_session(_remote_session_user())

    assert result is expected_active
