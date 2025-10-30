"""Authentication Service Module"""
from typing import Dict, Any, cast

import jwt
from fastapi import HTTPException
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.dialects.postgresql import insert, Insert as PGInsert
from keycloak import KeycloakOpenID
from keycloak.exceptions import KeycloakError

from app.config import Config, logger
from app.utils.auth_client import get_keycloak_client  # 동기 클라이언트 생성 함수
from app.utils.security import encrypt_token
from app.utils.user import get_expiry_datetime
from app.models.users import User
from app.schemas.users import LoginCallbackReq


async def perform_token_exchange(relay_access_token: str) -> Dict[str, Any]:
    """Relay Access Token을 사용하여 Keycloak과 동기적으로 Token Exchange를 수행합니다."""
    logger.info("Performing Token Exchange using sync KeycloakOpenID...")
    kc: KeycloakOpenID = get_keycloak_client()

    try:
        te = await kc.a_exchange_token(
            token=relay_access_token,
            subject_token_type="urn:ietf:params:oauth:token-type:access_token",
            # 1. requested_token_type은 access_token으로 유지
            requested_token_type="urn:ietf:params:oauth:token-type:access_token",
            audience=Config.KC_CLIENT_ID,
            # 2. scope에 'offline_access'만 추가
            scope="openid profile email offline_access",
        )
        logger.info("Token Exchange successful using sync client.")
        logger.debug("Token Exchange response: %s", te)
        # te 에는 이제 'access_token'과 'refresh_token'이 모두 포함됩니다.
        return te
    except KeycloakError as e:
        logger.error(
            "Keycloak Token exchange failed: Status Code=%s, Error=%s, Details=%s",
            e.response_code,
            e.error_message,
            e.response_body.decode() if isinstance(e.response_body, bytes) else ""
        )
        error_detail = (
            "token_exchange_failed: %s",
            e.error_message or e.response_body.decode() if isinstance(e.response_body, bytes) else ''
        )
        raise HTTPException(status_code=502, detail=error_detail) from e
    except Exception as e:
        logger.exception(f"Unexpected error during token exchange: {e}")
        raise HTTPException(
            status_code=502, detail=f"token_exchange_failed: {e}"
        ) from e


async def handle_token_exchange(relay_access_token: str) -> Dict[str, Any]:
    """Relay Access Token을 사용하여 Keycloak Token Exchange를 수행하고 결과를 반환합니다.

    offline_access 스코프를 포함해야합니다.
    """
    try:
        # [주의] perform_token_exchange는 scope='offline_access' 포함 필수
        token_exchange_result = await perform_token_exchange(relay_access_token)
    except Exception as e:
        logger.error(f"Token Exchange failed during handle_token_exchange: {e}")
        raise HTTPException(status_code=Config.HttpStatus.BAD_GATEWAY, detail="Token Exchange failed") from e

    # 필수 필드 확인 (access_token, refresh_token, expires_in, refresh_expires_in)
    required_keys = ["access_token", "refresh_token", "expires_in", "refresh_expires_in"]
    if not all(key in token_exchange_result for key in required_keys):
        logger.error(
            f"Token Exchange result missing required fields. "
            f"Result: {token_exchange_result.keys()}"
        )
        raise HTTPException(
            status_code=Config.HttpStatus.INTERNAL_SERVER_ERROR,
            detail="Token exchange response missing required fields. Check 'offline_access' scope.",
        )
    logger.info("Token Exchange successful.")
    return token_exchange_result


def extract_keycloak_sub(access_token: str) -> str:
    """Access Token (JWT)에서 Keycloak 'sub' 클레임을 추출합니다."""
    try:
        # 서명 검증 없이 페이로드만 디코딩
        token_payload: dict = jwt.decode(access_token, options={"verify_signature": False})
        keycloak_sub = token_payload.get("sub")
        if not keycloak_sub:
            raise ValueError("Sub (user ID) missing in JWT payload")
        logger.info(f"Extracted keycloak_sub: {keycloak_sub}")
        return keycloak_sub
    except Exception as e:
        logger.error(f"Failed to decode access token or extract sub: {e}")
        raise HTTPException(status_code=Config.HttpStatus.INTERNAL_SERVER_ERROR, detail="Invalid access token payload") from e


async def map_keycloak_user(  # noqa: PLR0913
        db: AsyncSession,
        kakao_id: str,
        keycloak_sub: str,
        access_token: str,
        refresh_token: str,
        expires_in: int,
        refresh_expires_in: int,
        plusfriend_user_key: str | None = None,
    ) -> User:
    """keycloak_sub 기준으로 User 모델을 찾아 암호화된 토큰들과 만료 시간을 저장(Upsert)합니다."""
    # 1. 토큰 암호화 (Access Token 포함)
    try:
        encrypted_access_token = encrypt_token(access_token)
        encrypted_refresh_token = encrypt_token(refresh_token)
    except Exception as e:
        logger.error(f"Token encryption failed for keycloak_sub={keycloak_sub}: {e}")
        raise HTTPException(status_code=500, detail="Token encryption failed") from e

    # 2. Upsert 값 준비
    insert_stmt = cast(PGInsert, insert(User).values(
        keycloak_sub=keycloak_sub,
        kakao_id=kakao_id,
        plusfriend_user_key=plusfriend_user_key,
        access_token=encrypted_access_token,
        refresh_token=encrypted_refresh_token,
        access_token_expires_at=get_expiry_datetime(expires_in),
        refresh_token_expires_at=get_expiry_datetime(refresh_expires_in),
    ))

    # 3. PostgreSQL Upsert 실행
    # `keycloak_sub` 컬럼에 Unique Constraint 'uq_keycloak_sub'가 있다고 가정
    update_values = {
        User.kakao_id: insert_stmt.excluded.kakao_id,
        User.plusfriend_user_key: insert_stmt.excluded.plusfriend_user_key,
        User.access_token: insert_stmt.excluded.access_token,
        User.refresh_token: insert_stmt.excluded.refresh_token,
        User.access_token_expires_at: insert_stmt.excluded.access_token_expires_at,
        User.refresh_token_expires_at: insert_stmt.excluded.refresh_token_expires_at,
    }

    # 충돌 시 업데이트할 값들 (id와 keycloak_sub 제외)
    upsert_stmt = insert_stmt.on_conflict_do_update(
        constraint='uq_keycloak_sub', # Unique Constraint 이름
        set_=update_values
    )

    try:
        await db.execute(upsert_stmt)
        await db.commit()

        # Upsert 후 레코드 다시 조회 (ID 등 확인 위해)
        result = await db.execute(select(User).where(User.keycloak_sub == keycloak_sub))
        user_map = result.scalar_one_or_none()

        if not user_map:
            logger.error(f"Upsert seemed successful but failed to fetch User Model for keycloak_sub={keycloak_sub}")
            raise HTTPException(status_code=500, detail="Failed to retrieve mapping after upsert")

        logger.info(f"User Model upsert successful for keycloak_sub={keycloak_sub}, User Model ID: {user_map.id}")
        return user_map

    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to upsert user mapping for keycloak_sub={keycloak_sub}: {e}")
        raise HTTPException(status_code=500, detail="Database commit failed during mapping upsert") from e


async def get_keycloak_sub_by_kakao_id(
    db: AsyncSession, kakao_user_id: str
) -> str | None:
    """Kakao User ID로 Keycloak Sub ID를 조회합니다."""
    stmt = select(User.keycloak_sub).where(User.kakao_id == kakao_user_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()
