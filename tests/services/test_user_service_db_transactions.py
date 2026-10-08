from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import HTTPException
from httpx import AsyncClient
from keycloak.exceptions import KeycloakAuthenticationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.database import AsyncSessionLocal
from app.models.users import User
from app.services import user_service
from app.utils.kakao import LoginRequiredError
from app.utils.security import decrypt_token, encrypt_token


@pytest_asyncio.fixture
async def engine(tmp_path: Path) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'users.db'}",
        pool_size=1,
        max_overflow=0,
        pool_timeout=0.05,
    )
    try:
        async with engine.begin() as connection:
            await connection.run_sync(User.__table__.create)
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def user_session(engine: AsyncEngine) -> AsyncIterator[tuple[AsyncSession, User]]:
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal(bind=engine) as db:
        db.add(
            User(
                kakao_id="kakao-user",
                keycloak_id="keycloak-user",
                access_token=encrypt_token("old-access"),
                refresh_token=encrypt_token("old-refresh"),
                access_token_expires_at=now + timedelta(minutes=5),
                refresh_token_expires_at=now + timedelta(days=30),
            )
        )
        await db.commit()

    async with AsyncSessionLocal(bind=engine) as db:
        user = await user_service.get_user("kakao-user", db)
        yield db, user


async def assert_connection_available(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        assert (await connection.execute(select(User.id))).scalar_one() == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "outcome", ["success", "unauthorized", "temporary", "malformed"]
)
async def test_refresh_releases_connection_and_preserves_expected_auth_state(
    engine: AsyncEngine,
    user_session: tuple[AsyncSession, User],
    monkeypatch: pytest.MonkeyPatch,
    outcome: str,
) -> None:
    db, user = user_session

    async def refresh(refresh_value: str, *, keycloak_sub: str) -> dict[str, object]:
        assert refresh_value == "old-refresh"
        assert keycloak_sub == "keycloak-user"
        await assert_connection_available(engine)
        if outcome == "unauthorized":
            raise HTTPException(status_code=401, detail="session_expired")
        if outcome == "temporary":
            raise HTTPException(status_code=500, detail="temporary_error")
        if outcome == "malformed":
            return {}
        return {
            "access_token": "new-access",
            "refresh_token": "new-refresh",
            "expires_in": 300,
            "refresh_expires_in": 3600,
        }

    monkeypatch.setattr(user_service, "request_token_refresh", refresh)
    if outcome == "success":
        result = await user_service._perform_token_refresh(user, db)
        assert decrypt_token(result) == "new-access"
        assert user.access_token == result
    elif outcome == "unauthorized":
        with pytest.raises(LoginRequiredError):
            await user_service._perform_token_refresh(user, db)
    else:
        with pytest.raises(HTTPException) as exc_info:
            await user_service._perform_token_refresh(user, db)
        assert exc_info.value.status_code == 500

    assert not db.in_transaction()
    async with AsyncSessionLocal(bind=engine) as reader:
        stored = (await reader.execute(select(User))).scalar_one()
        if outcome == "unauthorized":
            assert stored.access_token is None
            assert stored.refresh_token is None
            assert stored.access_token_expires_at is None
            assert stored.refresh_token_expires_at is None
        else:
            assert stored.access_token is not None
            assert stored.refresh_token is not None
            expected_access = "new-access" if outcome == "success" else "old-access"
            expected_refresh = "new-refresh" if outcome == "success" else "old-refresh"
            assert decrypt_token(stored.access_token) == expected_access
            assert decrypt_token(stored.refresh_token) == expected_refresh


@pytest.mark.asyncio
@pytest.mark.parametrize("expired", [False, True])
async def test_userinfo_releases_connection_with_valid_or_refreshed_token(
    engine: AsyncEngine,
    user_session: tuple[AsyncSession, User],
    monkeypatch: pytest.MonkeyPatch,
    expired: bool,
) -> None:
    db, user = user_session
    if expired:
        user.access_token_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await db.commit()
        await db.refresh(user)

    async def refresh(refresh_value: str, *, keycloak_sub: str) -> dict[str, object]:
        assert expired
        assert refresh_value == "old-refresh"
        assert keycloak_sub == "keycloak-user"
        await assert_connection_available(engine)
        return {
            "access_token": "new-access",
            "refresh_token": "new-refresh",
            "expires_in": 300,
            "refresh_expires_in": 3600,
        }

    async def userinfo(*, token: str) -> dict[str, object]:
        assert token == ("new-access" if expired else "old-access")
        await assert_connection_available(engine)
        return {"preferred_username": "tester", "email_verified": True}

    monkeypatch.setattr(user_service, "request_token_refresh", refresh)
    monkeypatch.setattr(
        user_service,
        "get_keycloak_client",
        lambda: SimpleNamespace(a_userinfo=userinfo),
    )
    async with AsyncClient() as client:
        result = await user_service.get_user_info(client, db, user)

    assert result.sub == "keycloak-user"
    assert result.preferred_username == "tester"
    assert result.email_verified is True
    assert not db.in_transaction()


@pytest.mark.asyncio
@pytest.mark.parametrize("exists", [True, False, None])
async def test_auth_failure_releases_connection_before_account_lookup(
    engine: AsyncEngine,
    user_session: tuple[AsyncSession, User],
    monkeypatch: pytest.MonkeyPatch,
    exists: bool | None,
) -> None:
    db, user = user_session

    async def user_exists(keycloak_sub: str) -> bool | None:
        assert keycloak_sub == "keycloak-user"
        await assert_connection_available(engine)
        return exists

    monkeypatch.setattr(user_service, "keycloak_user_exists", user_exists)
    error = KeycloakAuthenticationError(
        error_message="authentication failed", response_code=401
    )
    with pytest.raises(LoginRequiredError):
        await user_service.handle_keycloak_authentication_failure(user, db, error)

    await db.close()
    async with AsyncSessionLocal(bind=engine) as reader:
        stored = (await reader.execute(select(User))).scalar_one_or_none()
        if exists is False:
            assert stored is None
        else:
            assert stored is not None
            assert stored.access_token is None
            assert stored.refresh_token is None
