"""User Service Module."""

from datetime import datetime, timezone, timedelta
from enum import StrEnum
from typing import Annotated, AsyncGenerator, NoReturn

import jwt
from fastapi import Depends, Header, HTTPException
from httpx import AsyncClient
from keycloak import KeycloakError
from keycloak.exceptions import KeycloakAuthenticationError
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from kakao_chatbot import Payload
from kakao_chatbot.response import KakaoResponse

from app.config import BlockID, Config, logger
from app.models.users import User
from app.schemas.user import UserSchema
from app.services.auth_service import (
    get_keycloak_client,
    keycloak_user_exists,
    request_token_refresh,
    get_expiry_datetime,
)
from app.utils.db import get_db
from app.utils.http import XUserIDClient
from app.utils.kakao import (
    KakaoError,
    LoginRequiredError,
    NotAuthenticated,
    UserIdentityConflictError,
    parse_payload,
)
from app.utils.security import decrypt_token, encrypt_token


class UserAuthCleanupMode(StrEnum):
    """사용자 인증 정리 방식을 정의합니다."""

    CLEAR_SESSION = "clear_session"
    DELETE_USER = "delete_user"


def _normalize_to_utc(dt: datetime) -> datetime:
    """Datetime 객체를 UTC 기준으로 변환합니다."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def has_active_login_session(user: User) -> bool:
    """저장된 refresh token 기준으로 재로그인 없이 사용 가능한 세션인지 확인합니다."""
    if not user.keycloak_id or not user.refresh_token or not user.refresh_token_expires_at:
        return False

    refresh_expires_at = _normalize_to_utc(user.refresh_token_expires_at)
    if refresh_expires_at <= datetime.now(timezone.utc):
        return False

    try:
        decrypt_token(user.refresh_token)
    except (ValueError, RuntimeError):
        return False

    return True
def _coerce_optional_str(value: object) -> str:
    """Keycloak 응답 필드를 문자열로 안전하게 정규화합니다."""
    return value if isinstance(value, str) else ""


def _coerce_bool(value: object) -> bool:
    """Keycloak 응답 필드를 불리언으로 안전하게 정규화합니다."""
    return value if isinstance(value, bool) else False


async def cleanup_user_auth_state(
    user: User,
    db: AsyncSession,
    *,
    mode: UserAuthCleanupMode,
    reason: str,
) -> None:
    """사용자 인증 상태를 공통 규칙으로 정리합니다.

    Args:
        user (User): 정리 대상 사용자 엔티티.
        db (AsyncSession): 데이터베이스 세션.
        mode (UserAuthCleanupMode): 세션 초기화 또는 사용자 연동 레코드 삭제 방식.
        reason (str): 정리 사유 로그용 문자열.
    """
    logger.info(
        "Cleaning up user auth state for reason=%s keycloak_sub=%s mode=%s",
        reason,
        user.keycloak_id,
        mode,
    )

    if mode is UserAuthCleanupMode.DELETE_USER:
        await db.delete(user)
        await db.commit()
        return

    user.access_token = None
    user.refresh_token = None
    user.access_token_expires_at = None
    user.refresh_token_expires_at = None
    await db.commit()
    await db.refresh(user)


async def handle_keycloak_authentication_failure(
    user: User,
    db: AsyncSession,
    error: KeycloakAuthenticationError,
) -> NoReturn:
    """Keycloak 인증 실패를 사용자 상태에 맞게 정리하고 재로그인을 유도합니다."""
    user_exists = keycloak_user_exists(user.keycloak_id)

    if user_exists is False:
        await cleanup_user_auth_state(
            user,
            db,
            mode=UserAuthCleanupMode.DELETE_USER,
            reason="keycloak_account_missing",
        )
        raise LoginRequiredError(
            message=(
                "연결된 계정을 찾을 수 없어 저장된 연동 정보를 정리했습니다. "
                '아래 로그인 버튼 또는 "로그인"을 입력해 다시 로그인해주세요.'
            )
        ) from error

    if user_exists is None:
        logger.warning(
            "Could not verify Keycloak user existence for sub=%s after authentication failure",
            user.keycloak_id,
        )

    await cleanup_user_auth_state(
        user,
        db,
        mode=UserAuthCleanupMode.CLEAR_SESSION,
        reason="keycloak_authentication_failed",
    )
    raise LoginRequiredError(
        message=(
            "사용자 인증 정보가 만료되었거나 더 이상 유효하지 않습니다. "
            '아래 로그인 버튼 또는 "로그인"을 입력해 다시 로그인해주세요.'
        )
    ) from error


async def _perform_token_refresh(user: User, db: AsyncSession) -> str:
    """Refresh Token을 사용해 Keycloak Access Token을 갱신합니다.

    Args:
        user (User): 토큰 갱신이 필요한 사용자 엔티티
        db (AsyncSession): 데이터베이스 세션

    Returns:
        str: 갱신된 Access Token '암호화' 문자열
    """
    login_response = KakaoResponse()
    login_response.add_quick_reply(
        label="로그인",
        action="block",
        block_id=BlockID.LOGIN,
    )
    if not user.refresh_token or not user.refresh_token_expires_at:
        logger.warning(
            "No refresh token available for keycloak_sub=%s", user.keycloak_id
        )
        raise LoginRequiredError(
            message='인증 정보를 찾을 수 없습니다. 아래 로그인 버튼 또는 "로그인"을 입력해 다시 로그인해주세요.'
        )

    refresh_expires_at = _normalize_to_utc(user.refresh_token_expires_at)
    now_utc = datetime.now(timezone.utc)
    if refresh_expires_at <= now_utc:
        logger.warning(
            "Refresh token expired for keycloak_sub=%s (expired_at=%s, now=%s)",
            user.keycloak_id,
            refresh_expires_at.isoformat(),
            now_utc.isoformat(),
        )
        raise LoginRequiredError(
            message='로그인 인증 기간이 만료되었습니다. 아래 로그인 버튼 또는 "로그인"을 입력해 다시 로그인해주세요.'
        )

    try:
        decrypted_refresh_token = decrypt_token(user.refresh_token)
    except (ValueError, RuntimeError) as exc:
        logger.error(
            "Failed to decrypt refresh token for keycloak_sub=%s: %s",
            user.keycloak_id,
            exc,
            exc_info=True,
        )
        raise LoginRequiredError(
            message='토큰 정보가 유효하지 않습니다. 아래 로그인 버튼 또는 "로그인"을 입력해 다시 로그인해주세요.'
        ) from exc

    try:
        token_response = await request_token_refresh(
            decrypted_refresh_token, keycloak_sub=user.keycloak_id
        )
    except HTTPException as exc:
        if exc.status_code != Config.HttpStatus.UNAUTHORIZED:
            raise

        logger.warning(
            "Token refresh requires re-login for keycloak_sub=%s",
            user.keycloak_id,
        )
        user.access_token = None
        user.refresh_token = None
        user.access_token_expires_at = None
        user.refresh_token_expires_at = None
        await db.commit()
        await db.refresh(user)
        raise LoginRequiredError(
            message='로그인 세션이 만료되었습니다. 아래 로그인 버튼 또는 "로그인"을 입력해 다시 로그인해주세요.'
        ) from exc

    try:
        new_access_token = token_response["access_token"]
        new_refresh_token = token_response["refresh_token"]
        expires_in = int(token_response["expires_in"])
        refresh_expires_in = int(token_response["refresh_expires_in"])

        encrypted_access_token = encrypt_token(str(new_access_token))
        encrypted_refresh_token = encrypt_token(str(new_refresh_token))

        user.access_token = encrypted_access_token
        user.refresh_token = encrypted_refresh_token
        user.access_token_expires_at = get_expiry_datetime(expires_in)
        user.refresh_token_expires_at = get_expiry_datetime(refresh_expires_in)

        await db.commit()
        await db.refresh(user)
        logger.info("Token refresh successful for keycloak_sub=%s", user.keycloak_id)
        return encrypted_access_token
    except (KeyError, ValueError, RuntimeError) as exc:
        await db.rollback()
        logger.error(
            "Token refresh response parsing or encryption failed: %s",
            exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=Config.HttpStatus.INTERNAL_SERVER_ERROR,
            detail="토큰 갱신 응답 처리 중 오류가 발생했습니다.",
        ) from exc


async def resolve_keycloak_context(user: User, db: AsyncSession) -> tuple[str, str]:
    """사용자 엔티티에 저장된 Keycloak id와 액세스 토큰을 반환합니다."""
    if not user.keycloak_id:
        raise LoginRequiredError(
            message=(
                "Keycloak 로그인이 완료되지 않았습니다. 아래 로그인 버튼 또는 "
                '"로그인"을 입력해 다시 로그인해주세요.'
            )
        )
    if not user.access_token or not user.access_token_expires_at:
        raise LoginRequiredError(
            message=(
                "Keycloak 액세스 토큰이 없습니다. 아래 로그인 버튼 또는 "
                '"로그인"을 입력해 다시 로그인해주세요.'
            )
        )

    expires_at = _normalize_to_utc(user.access_token_expires_at)
    now_with_buffer = datetime.now(timezone.utc) + timedelta(seconds=60)

    if expires_at <= now_with_buffer:
        # 토큰 만료 → 갱신 후 갱신된 암호화 토큰을 복호화하여 반환
        encrypted_access_token = await _perform_token_refresh(user, db)
        try:
            decrypted_access_token = decrypt_token(encrypted_access_token)
        except ValueError as exc:
            raise LoginRequiredError(
                message=(
                    "갱신된 토큰 정보가 유효하지 않습니다. 아래 로그인 버튼 또는 "
                    '"로그인"을 입력해 다시 로그인해주세요.'
                )
            ) from exc
        except RuntimeError as exc:
            logger.exception(
                "Unexpected error while decrypting refreshed access token for keycloak_sub=%s",
                user.keycloak_id,
            )
            raise KakaoError(
                "토큰 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요."
            ) from exc
    else:
        # 토큰 유효 → 기존 토큰 복호화
        try:
            decrypted_access_token = decrypt_token(user.access_token)
        except ValueError as exc:
            raise LoginRequiredError(
                message=(
                    "토큰 정보가 유효하지 않습니다. 아래 로그인 버튼 또는 "
                    '"로그인"을 입력해 다시 로그인해주세요.'
                )
            ) from exc
        except RuntimeError as exc:
            logger.exception(
                "Unexpected error while decrypting access token for keycloak_sub=%s",
                user.keycloak_id,
            )
            raise KakaoError(
                "토큰 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요."
            ) from exc

    keycloak_id = user.keycloak_id
    return keycloak_id, decrypted_access_token


async def get_keycloak_id_by_kakao_id(
    db: AsyncSession, kakao_user_id: str
) -> str | None:
    """Kakao User ID로 Keycloak ID를 조회합니다."""
    result = await db.execute(
        select(User.keycloak_id).where(User.kakao_id == kakao_user_id)
    )
    return result.scalar_one_or_none()


async def find_user(
    db: AsyncSession,
    kakao_id: str,
    *,
    plusfriend_user_key: str | None = None,
    app_user_id: str | None = None,
) -> User | None:
    """주어진 식별자들로 사용자를 1회 조회하고 충돌 여부를 판별합니다."""
    conditions = [User.kakao_id == kakao_id]

    if plusfriend_user_key:
        conditions.append(User.plusfriend_user_key == plusfriend_user_key)

    if app_user_id:
        conditions.append(User.app_user_id == app_user_id)

    result = await db.execute(
        select(User).where(or_(*conditions))
    )
    users = result.scalars().all()

    if not users:
        return None

    # 서로 다른 user가 2명 이상 나오면 충돌
    unique_user_ids = {user.id for user in users}
    if len(unique_user_ids) > 1:
        raise UserIdentityConflictError(
            message=(
                "사용자 정보가 충돌 상태입니다. 관리자에게 문의해주세요."
            )
        )

    return users[0]


async def get_user(
    kakao_id: str,
    db: AsyncSession,
    plusfriend_user_key: str | None = None,
    app_user_id: str | None = None,
) -> User:
    """주어진 식별자들로 사용자를 조회하고 필요 시 식별자 값을 동기화합니다."""
    user = await find_user(
        db=db,
        kakao_id=kakao_id,
        plusfriend_user_key=plusfriend_user_key,
        app_user_id=app_user_id,
    )

    if not user:
        raise NotAuthenticated()

    if (
        user.kakao_id != kakao_id
        or user.plusfriend_user_key != plusfriend_user_key
        or user.app_user_id != app_user_id
    ):
        user.kakao_id = kakao_id
        if plusfriend_user_key:
            user.plusfriend_user_key = plusfriend_user_key
        if app_user_id:
            user.app_user_id = app_user_id
        await db.commit()
        await db.refresh(user)
    return user


async def get_user_info(
    client: AsyncClient,
    db: AsyncSession,
    user: User,
):
    """Keycloak에서 사용자 정보를 조회합니다."""
    keycloak_sub, access_token = await resolve_keycloak_context(user, db)

    keycloak_client = get_keycloak_client()

    try:

        user_info: dict[str, object] = await keycloak_client.a_userinfo(
            token=access_token
        )

    except KeycloakAuthenticationError as exc:
        logger.warning(
            "Authentication error when fetching user info for keycloak_sub=%s: %s",
            keycloak_sub,
            exc,
        )
        await handle_keycloak_authentication_failure(user, db, exc)
    except KeycloakError as exc:
        logger.error(
            "Failed to fetch user info from Keycloak for sub=%s: %s",
            keycloak_sub,
            exc,
        )
        raise KakaoError(
            "사용자 정보 조회 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요."
        ) from exc

    return UserSchema(
        sub=keycloak_sub,
        name=_coerce_optional_str(
            user_info.get("username", user_info.get("preferred_username", ""))
        ),
        preferred_username=_coerce_optional_str(user_info.get("preferred_username", "")),
        email=_coerce_optional_str(user_info.get("email", "")),
        email_verified=_coerce_bool(user_info.get("email_verified", False)),
        first_name=_coerce_optional_str(
            user_info.get("first_name", user_info.get("given_name", ""))
        ),
        last_name=_coerce_optional_str(
            user_info.get("last_name", user_info.get("family_name", ""))
        ),
    )


async def get_current_user(
    payload: Annotated[Payload, Depends(parse_payload)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Payload 기반으로 현재 사용자를 조회합니다."""
    kakao_id = payload.user_request.user.id
    if not payload.user_request.user.properties:
        plusfriend_user_key = None
        app_user_id = None
    else:
        plusfriend_user_key = payload.user_request.user.properties.plusfriend_user_key
        app_user_id = payload.user_request.user.properties.app_user_id
    return await get_user(
        kakao_id,
        db,
        plusfriend_user_key=plusfriend_user_key,
        app_user_id=app_user_id,
    )


async def get_current_user_by_header(
    db: Annotated[AsyncSession, Depends(get_db)],
    x_user_id: str | None = Header(None, alias="X-User-ID"),
) -> User:
    """X-User-ID 헤더 값으로 사용자를 조회합니다."""
    if not x_user_id:
        raise HTTPException(
            status_code=Config.HttpStatus.UNAUTHORIZED,
            detail="X-User-ID 헤더가 필요합니다.",
        )

    result = await db.execute(select(User).where(User.keycloak_id == x_user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=Config.HttpStatus.NOT_FOUND,
            detail="사용자를 찾을 수 없습니다.",
        )

    return user


async def get_xuser_client_by_payload(
    payload: Annotated[Payload, Depends(parse_payload)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AsyncGenerator[XUserIDClient, None]:
    """카카오 Payload 기반으로 Keycloak 컨텍스트를 설정한 HTTP 클라이언트를 생성합니다."""
    user = await get_current_user(payload, db)
    user_id, access_token = await resolve_keycloak_context(user, db)
    logger.debug("Provide XUserIDClient for keycloak_sub=%s", user_id)
    async with XUserIDClient(
        user_id=user_id,
        access_token=access_token,
    ) as client:
        yield client


async def is_global_admin(client: AsyncClient) -> bool:
    """Access Token을 파싱하여 global_admin 역할을 확인합니다."""
    auth_header: str = client.headers.get("Authorization", "")
    if not auth_header or not auth_header.startswith("Bearer "):
        logger.warning(
            "is_global_admin: Missing or invalid Authorization header in client."
        )
        return False

    token = auth_header.split("Bearer ")[-1]

    try:
        payload = jwt.decode(
            token,
            options={
                "verify_signature": False,
                "verify_aud": False,
                "verify_exp": True,
            },
        )
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=Config.HttpStatus.UNAUTHORIZED,
            detail="Access token has expired.",
        ) from exc
    except jwt.DecodeError as exc:
        logger.error("is_global_admin: Failed to decode access token: %s", exc)
        return False
    except Exception as exc:  # noqa: BLE001
        logger.error("is_global_admin: Unexpected error decoding token: %s", exc)
        return False

    realm_access = payload.get("realm_access", {})
    roles = realm_access.get("roles", [])
    if not isinstance(roles, list):
        logger.warning("is_global_admin: 'realm_access.roles' claim is not a list.")
        return False

    is_admin = "global_admin" in roles
    logger.debug("is_global_admin check: %s (Roles: %s)", is_admin, roles)
    return is_admin


async def check_admin_user(
    user: User,
    client: AsyncClient,
    kakao_request: bool = True,
) -> bool:
    """사용자가 관리자 권한을 가지고 있는지 확인합니다."""
    if user.kakao_admin or await is_global_admin(client):
        return True
    exception = HTTPException(
        status_code=Config.HttpStatus.FORBIDDEN,
        detail="관리자 권한이 없습니다.",
    )
    if kakao_request:
        raise KakaoError(exception.detail)
    raise exception


async def get_admin_user(
    db: Annotated[AsyncSession, Depends(get_db)],
    client: Annotated[AsyncClient, Depends(get_xuser_client_by_payload)],
    payload: Annotated[Payload, Depends(parse_payload)],
) -> User:
    """현재 사용자가 관리자 권한을 가지고 있는지 확인하고 User 객체를 반환합니다."""
    user = await get_current_user(payload, db)
    await check_admin_user(user, client)
    return user


async def get_admin_user_by_header(
    db: Annotated[AsyncSession, Depends(get_db)],
    x_user_id: str | None = Header(None, alias="X-User-ID"),
) -> User:
    """헤더 기반으로 관리자 여부를 확인합니다."""
    user = await get_current_user_by_header(db, x_user_id)
    user_id, access_token = await resolve_keycloak_context(user, db)
    async with XUserIDClient(user_id=user_id, access_token=access_token) as client:
        await check_admin_user(user, client, kakao_request=False)
    return user
