from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from fastapi import HTTPException
import pytest

from app.services import user_service
from app.utils.kakao import LoginRequiredError
from app.utils.security import encrypt_token


class DummyDB:
    def __init__(self) -> None:
        self.committed = False
        self.refreshed = False
        self.rolled_back = False

    async def commit(self) -> None:
        self.committed = True

    async def refresh(self, _: object) -> None:
        self.refreshed = True

    async def rollback(self) -> None:
        self.rolled_back = True


def make_user(**overrides: object) -> SimpleNamespace:
    now = datetime.now(timezone.utc)
    user = SimpleNamespace(
        keycloak_id="keycloak-sub-1",
        access_token=encrypt_token("access-token"),
        refresh_token=encrypt_token("refresh-token"),
        access_token_expires_at=now + timedelta(minutes=5),
        refresh_token_expires_at=now + timedelta(days=30),
    )
    for key, value in overrides.items():
        setattr(user, key, value)
    return user


def test_has_active_login_session_returns_true_for_usable_refresh_token() -> None:
    assert user_service.has_active_login_session(make_user()) is True


def test_has_active_login_session_returns_false_for_expired_refresh_token() -> None:
    assert (
        user_service.has_active_login_session(
            make_user(refresh_token_expires_at=datetime.now(timezone.utc))
        )
        is False
    )


@pytest.mark.asyncio
async def test_perform_token_refresh_clears_auth_state_on_terminal_refresh_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_request_token_refresh(*_: object, **__: object) -> dict[str, object]:
        raise HTTPException(status_code=401, detail="session_expired")

    monkeypatch.setattr(user_service, "request_token_refresh", fake_request_token_refresh)

    user = make_user()
    db = DummyDB()

    with pytest.raises(LoginRequiredError) as exc_info:
        await user_service._perform_token_refresh(user, db)

    assert exc_info.value.message is not None
    assert "로그인 세션이 만료되었습니다" in exc_info.value.message
    assert user.access_token is None
    assert user.refresh_token is None
    assert user.access_token_expires_at is None
    assert user.refresh_token_expires_at is None
    assert db.committed is True
    assert db.refreshed is True


@pytest.mark.asyncio
async def test_perform_token_refresh_keeps_auth_state_on_non_terminal_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_request_token_refresh(*_: object, **__: object) -> dict[str, object]:
        raise HTTPException(status_code=500, detail="temporary_error")

    monkeypatch.setattr(user_service, "request_token_refresh", fake_request_token_refresh)

    user = make_user()
    original_access_token = user.access_token
    original_refresh_token = user.refresh_token
    db = DummyDB()

    with pytest.raises(HTTPException, match="temporary_error"):
        await user_service._perform_token_refresh(user, db)

    assert user.access_token == original_access_token
    assert user.refresh_token == original_refresh_token
    assert db.committed is False
    assert db.refreshed is False
