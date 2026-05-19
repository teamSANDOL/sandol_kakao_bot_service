from datetime import datetime, timedelta, timezone
from collections.abc import AsyncGenerator

from fastapi import HTTPException
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.models.users import User
from app.services import auth_service
from app.services.auth_service import map_keycloak_user
from app.utils.security import encrypt_token


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_map_keycloak_user_allows_relink_for_stale_kakao_mapping(
    db_session: AsyncSession,
) -> None:
    stale_user = User(
        keycloak_id="old-sub",
        kakao_id="kakao-user-1",
        plusfriend_user_key=None,
        app_user_id=None,
        kakao_admin=False,
        access_token=None,
        refresh_token=None,
        access_token_expires_at=None,
        refresh_token_expires_at=None,
    )
    db_session.add(stale_user)
    await db_session.commit()

    updated_user = await map_keycloak_user(
        db=db_session,
        kakao_id="kakao-user-1",
        keycloak_sub="new-sub",
        decrypted_access_token="new-access-token",
        decrypted_refresh_token="new-refresh-token",
        expires_in=600,
        refresh_expires_in=3600,
    )

    assert updated_user.id == stale_user.id
    assert updated_user.keycloak_id == "new-sub"
    assert updated_user.access_token is not None
    assert updated_user.refresh_token is not None


@pytest.mark.asyncio
async def test_map_keycloak_user_preserves_conflict_for_active_mapping(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_request_token_refresh(*_: object, **__: object) -> dict[str, object]:
        return {
            "access_token": "refreshed-access-token",
            "refresh_token": "refreshed-refresh-token",
            "expires_in": 600,
            "refresh_expires_in": 3600,
        }

    monkeypatch.setattr(
        auth_service,
        "request_token_refresh",
        fake_request_token_refresh,
    )

    active_user = User(
        keycloak_id="old-sub",
        kakao_id="kakao-user-1",
        plusfriend_user_key=None,
        app_user_id=None,
        kakao_admin=False,
        access_token=encrypt_token("access-token"),
        refresh_token=encrypt_token("refresh-token"),
        access_token_expires_at=datetime.now(timezone.utc) - timedelta(minutes=10),
        refresh_token_expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db_session.add(active_user)
    await db_session.commit()

    with pytest.raises(HTTPException, match="이미 다른 Keycloak 계정과 연결") as exc_info:
        await map_keycloak_user(
            db=db_session,
            kakao_id="kakao-user-1",
            keycloak_sub="new-sub",
            decrypted_access_token="new-access-token",
            decrypted_refresh_token="new-refresh-token",
            expires_in=600,
            refresh_expires_in=3600,
        )

    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_map_keycloak_user_allows_relink_when_remote_refresh_is_invalid(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_request_token_refresh(*_: object, **__: object) -> dict[str, object]:
        raise HTTPException(status_code=401, detail="session_expired")

    monkeypatch.setattr(
        auth_service,
        "request_token_refresh",
        fake_request_token_refresh,
    )

    remotely_stale_user = User(
        keycloak_id="old-sub",
        kakao_id="kakao-user-1",
        plusfriend_user_key=None,
        app_user_id=None,
        kakao_admin=False,
        access_token=encrypt_token("access-token"),
        refresh_token=encrypt_token("refresh-token"),
        access_token_expires_at=datetime.now(timezone.utc) - timedelta(minutes=10),
        refresh_token_expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db_session.add(remotely_stale_user)
    await db_session.commit()

    updated_user = await map_keycloak_user(
        db=db_session,
        kakao_id="kakao-user-1",
        keycloak_sub="new-sub",
        decrypted_access_token="new-access-token",
        decrypted_refresh_token="new-refresh-token",
        expires_in=600,
        refresh_expires_in=3600,
    )

    assert updated_user.id == remotely_stale_user.id
    assert updated_user.keycloak_id == "new-sub"
