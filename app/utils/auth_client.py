# app/utils/auth_client.py
import base64
import hashlib
import time
import hmac
import json
from datetime import datetime, timezone
from typing import Annotated, AsyncGenerator, Dict, Any

from diskcache import FanoutCache
from fastapi import Depends, HTTPException
from keycloak import KeycloakOpenID
from sqlalchemy.ext.asyncio import AsyncSession

from kakao_chatbot import Payload

from app.config import logger
from app.config.config import Config, CACHE_DIR
from app.models.users import User
from app.schemas.users import LoginCallbackReq
from app.utils.db import get_db
from app.utils.http import XUserIDClient
from app.utils.kakao import parse_payload
from app.utils.security import decrypt_token
from app.utils.user import get_current_user

# --- Nonce 검증 로직 추가 (diskcache 사용) ---
_NONCE_CACHE = FanoutCache(directory=CACHE_DIR, shards=8)


def _canonical_json(data: Dict[str, Any]) -> str:
    """HMAC 서명을 위한 정규화 JSON 문자열.

    Args:
        data: 페이로드 dict.

    Returns:
        정렬된 키 순서로 직렬화된 JSON 문자열.
    """
    return json.dumps(data, separators=(",", ":"), sort_keys=True, ensure_ascii=False)


def sign_payload(payload: LoginCallbackReq, secret: str) -> str:
    """HMAC-SHA256 서명 생성.

    Args:
        payload: 서명 대상 페이로드.

    Returns:
        base64url 인코딩된 서명 문자열.
    """
    canonical_json = _canonical_json(
        payload.model_dump()
    )  # 포맷 정규화를 위해 pydantic.model_dump_json()이 아닌 별도 함수 사용
    mac = hmac.new(
        secret.encode("utf-8"), canonical_json.encode("utf-8"), hashlib.sha256
    )
    return base64.urlsafe_b64encode(mac.digest()).decode()


def verify_relay_signature(header_sig: str | None, payload: LoginCallbackReq) -> None:
    """X-Relay-Signature 헤더를 검증합니다.

    Args:
        header_sig (str | None): X-Relay-Signature 헤더 값
        payload (LoginCallbackReq): 콜백 요청 데이터

    Raises:
        HTTPException: 서명 검증 실패 시
    """
    if header_sig is None:
        raise HTTPException(
            status_code=Config.HttpStatus.UNAUTHORIZED,
            detail="Missing X-Relay-Signature header",
        )
    secret = Config.RELAY_CLIENT_SECRETS
    expect = sign_payload(payload, secret)
    if not hmac.compare_digest(header_sig, expect):
        raise HTTPException(
            status_code=Config.HttpStatus.UNAUTHORIZED,
            detail="Invalid X-Relay-Signature header",
        )


def verify_timestamp(ts: int, tolerance: int = Config.NONCE_TTL_SECONDS) -> None:
    """타임스탬프가 현재 시간과 허용 오차 범위 내에 있는지 검증합니다.

    Args:
        ts (int): 검증할 타임스탬프 (초 단위)
        tolerance (int): 허용 오차 범위 (초 단위, 기본값: 300초)

    Raises:
        HTTPException: 타임스탬프가 허용 오차 범위를 벗어날 경우
    """
    now = int(time.time())
    if abs(now - ts) > tolerance:
        raise HTTPException(
            status_code=Config.HttpStatus.UNAUTHORIZED,
            detail="Timestamp is out of acceptable range",
        )


def mark_nonce_once(nonce: str) -> None:
    """nonce를 diskcache를 이용해 1회용으로 마킹. 중복 사용 시 거부.

    Args:
        nonce: 고유 nonce 문자열.
        ttl: 만료(초).

    Raises:
        HTTPException: 재사용된 nonce 또는 누락 시.
    """
    if not nonce:
        raise HTTPException(status_code=400, detail="missing_nonce")

    was_added = _NONCE_CACHE.add(
        key=nonce,
        value=int(time.time()),  # 값은 중요하지 않음 (현재 시간 저장)
        expire=Config.NONCE_TTL_SECONDS,  # TTL이 지나면 자동 삭제됨
    )

    if not was_added:
        # 키가 이미 존재했다는 의미 (재전송 공격)
        raise HTTPException(status_code=400, detail="reused_nonce")


# --- Keycloak 클라이언트 생성 ---
def get_keycloak_client() -> KeycloakOpenID:
    """동기 KeycloakOpenID 인스턴스를 생성합니다."""
    return KeycloakOpenID(
        server_url=Config.KC_SERVER_URL,
        realm_name=Config.KC_REALM,
        client_id=Config.KC_CLIENT_ID,
        client_secret_key=Config.KC_CLIENT_SECRET,
        timeout=10,
    )


def _normalize_to_utc(dt: datetime) -> datetime:
    """datetime 객체를 UTC 기반으로 정규화합니다.

    Args:
        dt (datetime): 정규화할 시간 정보.

    Returns:
        datetime: UTC 시간대가 적용된 datetime 객체.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def resolve_keycloak_context(user: User) -> tuple[str, str]:
    """사용자 엔티티에서 Keycloak `sub`와 액세스 토큰을 추출합니다.

    Args:
        user (User): Keycloak 토큰 정보를 포함하는 사용자 엔티티.

    Returns:
        tuple[str, str]: Keycloak `sub`와 복호화된 액세스 토큰.

    Raises:
        HTTPException: Keycloak 정보가 없거나 토큰이 만료·손상된 경우.
    """
    if not user.keycloak_sub:
        logger.info(
            "Keycloak context missing for kakao_id=%s", getattr(user, "kakao_id", None)
        )
        raise HTTPException(
            status_code=Config.HttpStatus.UNAUTHORIZED,
            detail="Keycloak 로그인이 완료되지 않았습니다. 먼저 로그인 절차를 진행해주세요.",
        )
    if not user.access_token or not user.access_token_expires_at:
        logger.warning(
            "Access token missing for keycloak_sub=%s", user.keycloak_sub
        )
        raise HTTPException(
            status_code=Config.HttpStatus.UNAUTHORIZED,
            detail="Keycloak 액세스 토큰이 없습니다. 다시 로그인해주세요.",
        )

    expires_at = _normalize_to_utc(user.access_token_expires_at)
    now_utc = datetime.now(timezone.utc)
    if expires_at <= now_utc:
        logger.info(
            "Access token expired for keycloak_sub=%s (expired_at=%s, now=%s)",
            user.keycloak_sub,
            expires_at.isoformat(),
            now_utc.isoformat(),
        )
        raise HTTPException(
            status_code=Config.HttpStatus.UNAUTHORIZED,
            detail="Keycloak 액세스 토큰이 만료되었습니다. 다시 로그인해주세요.",
        )

    try:
        access_token = decrypt_token(user.access_token)
    except ValueError as exc:
        logger.warning(
            "Failed to decrypt access token for keycloak_sub=%s", user.keycloak_sub
        )
        raise HTTPException(
            status_code=Config.HttpStatus.UNAUTHORIZED,
            detail="토큰 정보가 유효하지 않습니다. 다시 로그인해주세요.",
        ) from exc
    except RuntimeError as exc:
        logger.exception(
            "Unexpected error while decrypting access token for keycloak_sub=%s",
            user.keycloak_sub,
        )
        raise HTTPException(
            status_code=Config.HttpStatus.INTERNAL_SERVER_ERROR,
            detail="토큰 복호화 중 오류가 발생했습니다.",
        ) from exc

    return user.keycloak_sub, access_token


async def get_xuser_client_by_payload(
    payload: Annotated[Payload, Depends(parse_payload)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AsyncGenerator[XUserIDClient, None]:
    """카카오 페이로드 기반으로 Keycloak 컨텍스트가 포함된 클라이언트를 생성합니다.

    Args:
        payload (Payload): 카카오 챗봇에서 전달된 요청 페이로드.
        db (AsyncSession): 사용자 정보를 조회할 데이터베이스 세션.

    Yields:
        XUserIDClient: Keycloak `sub` 및 액세스 토큰이 설정된 HTTP 클라이언트.

    Raises:
        HTTPException: Keycloak 로그인 정보가 없거나 토큰이 만료된 경우.
    """
    user = await get_current_user(payload, db)
    user_sub, access_token = resolve_keycloak_context(user)
    logger.debug("Provide XUserIDClient for keycloak_sub=%s", user_sub)
    async with XUserIDClient(
        user_sub=user_sub,
        access_token=access_token,
    ) as client:
        yield client


async def get_service_xuser_client() -> AsyncGenerator[XUserIDClient, None]:
    """서비스 계정으로 외부 API를 호출하기 위한 클라이언트를 생성합니다.

    Returns:
        XUserIDClient: 서비스용 Keycloak 정보가 포함된 HTTP 클라이언트.
    """
    if not Config.SERVICE_ACCOUNT_TOKEN:
        logger.debug("SERVICE_ACCOUNT_TOKEN이 설정되지 않았습니다. 무인증 호출을 시도합니다.")
    async with XUserIDClient(
        Config.SERVICE_ACCOUNT_SUB,
        access_token=Config.SERVICE_ACCOUNT_TOKEN,
        token_type=Config.SERVICE_ACCOUNT_TOKEN_TYPE,
    ) as client:
        yield client
