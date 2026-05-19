from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import cast

import pytest
from keycloak.exceptions import KeycloakAuthenticationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.users import User
from app.services import user_service
from app.utils.kakao import LoginRequiredError
from app.utils.security import encrypt_token


class DummyDB:
    def __init__(self) -> None:
        self.committed = False
        self.refreshed = False
        self.deleted_user: object | None = None

    async def commit(self) -> None:
        self.committed = True

    async def refresh(self, _: object) -> None:
        self.refreshed = True

    async def delete(self, user: object) -> None:
        self.deleted_user = user


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


@pytest.mark.asyncio
async def test_handle_keycloak_authentication_failure_deletes_user_on_missing_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = make_user()
    db = DummyDB()
    error = KeycloakAuthenticationError(
        error_message="authentication failed",
        response_code=401,
    )
    monkeypatch.setattr(user_service, "keycloak_user_exists", lambda *_: False)

    with pytest.raises(LoginRequiredError) as exc_info:
        await user_service.handle_keycloak_authentication_failure(
            cast(User, user),
            cast(AsyncSession, cast(object, db)),
            error,
        )

    assert exc_info.value.message is not None
    assert "연동 정보를 정리했습니다" in exc_info.value.message
    assert db.deleted_user is user
    assert db.committed is True
    assert db.refreshed is False


@pytest.mark.asyncio
async def test_handle_keycloak_authentication_failure_clears_session_on_generic_auth_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = make_user()
    db = DummyDB()
    error = KeycloakAuthenticationError(
        error_message="authentication failed",
        response_code=401,
    )
    monkeypatch.setattr(user_service, "keycloak_user_exists", lambda *_: True)

    with pytest.raises(LoginRequiredError) as exc_info:
        await user_service.handle_keycloak_authentication_failure(
            cast(User, user),
            cast(AsyncSession, cast(object, db)),
            error,
        )

    assert exc_info.value.message is not None
    assert "더 이상 유효하지 않습니다" in exc_info.value.message
    assert user.access_token is None
    assert user.refresh_token is None
    assert user.access_token_expires_at is None
    assert user.refresh_token_expires_at is None
    assert db.deleted_user is None
    assert db.committed is True
    assert db.refreshed is True


@pytest.mark.asyncio
async def test_handle_keycloak_authentication_failure_does_not_delete_user_when_existence_is_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = make_user()
    db = DummyDB()
    error = KeycloakAuthenticationError(
        error_message="authentication failed",
        response_code=401,
    )
    monkeypatch.setattr(user_service, "keycloak_user_exists", lambda *_: None)

    with pytest.raises(LoginRequiredError):
        await user_service.handle_keycloak_authentication_failure(
            cast(User, user),
            cast(AsyncSession, cast(object, db)),
            error,
        )

    assert db.deleted_user is None
    assert user.access_token is None
    assert user.refresh_token is None
    assert db.committed is True
    assert db.refreshed is True
