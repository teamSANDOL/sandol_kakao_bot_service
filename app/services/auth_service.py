"""Authentication Service Module."""

from typing import Any
import base64
import hashlib
import hmac
import json
import time
from datetime import datetime, timezone, timedelta

from aiosqlite import IntegrityError
import jwt
from diskcache import FanoutCache  # type: ignore[import-untyped]
from pydantic import HttpUrl
from fastapi import HTTPException
from httpx import AsyncClient, HTTPStatusError
from keycloak import KeycloakOpenID
from keycloak.exceptions import KeycloakError
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from kakao_chatbot import Payload

from app.config import Config, logger
from app.config.config import CACHE_DIR
from app.schemas.auth import IssueLinkReq, IssueLinkRes, LoginCallbackReq
from app.models.users import User
from app.utils.security import encrypt_token

_NONCE_CACHE = FanoutCache(directory=CACHE_DIR, shards=8)


def get_keycloak_client() -> KeycloakOpenID:
    """동기 KeycloakOpenID 인스턴스를 생성합니다."""
    return KeycloakOpenID(
        server_url=Config.KC_SERVER_URL,
        realm_name=Config.KC_REALM,
        client_id=Config.KC_CLIENT_ID,
        client_secret_key=Config.KC_CLIENT_SECRET,
        timeout=10,
    )


def _canonical_json(data: dict[str, Any]) -> str:
    """HMAC 서명을 위한 정규화 JSON 문자열."""
    return json.dumps(data, separators=(",", ":"), sort_keys=True, ensure_ascii=False)


def sign_payload(payload: LoginCallbackReq, secret: str) -> str:
    """HMAC-SHA256 서명 생성."""
    canonical_json = _canonical_json(payload.model_dump())
    mac = hmac.new(
        secret.encode("utf-8"),
        canonical_json.encode("utf-8"),
        hashlib.sha256,
    )
    return base64.urlsafe_b64encode(mac.digest()).decode().rstrip("=")


def verify_relay_signature(header_sig: str | None, payload: LoginCallbackReq) -> None:
    """X-Relay-Signature 헤더를 검증합니다."""
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
    """타임스탬프가 허용 범위인지 검증합니다."""
    now = int(time.time())
    if abs(now - ts) > tolerance:
        raise HTTPException(
            status_code=Config.HttpStatus.UNAUTHORIZED,
            detail="Timestamp is out of acceptable range",
        )


def mark_nonce_once(nonce: str) -> None:
    """nonce를 1회용으로 체크합니다."""
    if not nonce:
        raise HTTPException(status_code=400, detail="missing_nonce")

    was_added = _NONCE_CACHE.add(
        key=nonce,
        value=int(time.time()),
        expire=Config.NONCE_TTL_SECONDS,
    )

    if not was_added:
        raise HTTPException(status_code=400, detail="reused_nonce")


def extract_keycloak_sub(decrypted_access_token: str) -> str:
    """Access Token에서 Keycloak `sub` 값을 추출합니다."""
    try:
        token_payload: dict = jwt.decode(
            decrypted_access_token, options={"verify_signature": False}
        )
    except Exception as exc:
        logger.error("Failed to decode access token: %s", exc)
        raise HTTPException(
            status_code=Config.HttpStatus.INTERNAL_SERVER_ERROR,
            detail="Invalid access token payload",
        ) from exc

    keycloak_sub = token_payload.get("sub")
    if not keycloak_sub:
        raise HTTPException(
            status_code=Config.HttpStatus.INTERNAL_SERVER_ERROR,
            detail="Sub (user ID) missing in JWT payload",
        )
    return keycloak_sub


def get_expiry_datetime(expires_in: int) -> datetime:
    """현재 시간 기준 expires_in 초 후의 만료 시각을 계산합니다.

    Offline Token의 경우 expires_in=0으로 반환되며, 이는 무제한을 의미합니다.
    이 경우 충분히 긴 기간(10년)을 설정합니다.
    """
    if expires_in == 0:
        # Offline Token: 무제한 (10년으로 설정)
        return datetime.now(timezone.utc) + timedelta(days=365 * 10)
    return datetime.now(timezone.utc) + timedelta(seconds=expires_in)


async def request_token_refresh(
    refresh_token: str, *, keycloak_sub: str | None = None
) -> dict[str, Any]:
    """Keycloak 클라이언트를 사용해 Refresh Token으로 토큰을 갱신합니다."""
    kc: KeycloakOpenID = get_keycloak_client()

    try:
        # python-keycloak이 내부에서 /token 엔드포인트를 호출
        token_data: dict[str, Any] = kc.refresh_token(refresh_token)
        logger.debug(
            "Token refresh via Keycloak client succeeded for keycloak_sub=%s",
            keycloak_sub,
        )
        return token_data

    except KeycloakError as exc:
        # python-keycloak 공통 예외
        body = (
            exc.response_body.decode()
            if isinstance(exc.response_body, (bytes, bytearray))
            else exc.response_body
        )
        logger.error(
            "Keycloak token refresh failed via client "
            "(status_code=%s) for keycloak_sub=%s: %s",
            exc.response_code,
            keycloak_sub,
            body,
        )

        if exc.response_code == Config.HttpStatus.BAD_REQUEST:
            # invalid_grant 등 → 세션 만료 처리
            raise HTTPException(
                status_code=Config.HttpStatus.UNAUTHORIZED,
                detail="인증 세션이 만료되었습니다. 다시 로그인해주세요.",
            ) from exc

        raise HTTPException(
            status_code=Config.HttpStatus.INTERNAL_SERVER_ERROR,
            detail="토큰 갱신 중 서버 오류가 발생했습니다.",
        ) from exc

    except Exception as exc:  # noqa: BLE001
        logger.error("Token refresh via Keycloak client failed: %s", exc)
        raise HTTPException(
            status_code=Config.HttpStatus.INTERNAL_SERVER_ERROR,
            detail="토큰 갱신 요청 중 오류가 발생했습니다.",
        ) from exc


async def generate_login_link(payload: Payload, client: AsyncClient) -> IssueLinkRes:
    """로그인 링크를 auth-relay로부터 발급받습니다."""
    chatbot_user_id = payload.user_id
    if chatbot_user_id is None:
        raise HTTPException(
            status_code=Config.HttpStatus.BAD_REQUEST,
            detail="Missing user id in payload",
        )

    request_payload = IssueLinkReq(
        chatbot_user_id=chatbot_user_id,
        callback_url=HttpUrl(Config.LOGIN_CALLBACK_URL),
        client_key=Config.KC_CLIENT_ID,
        redirect_after=HttpUrl(Config.LOGIN_REDIRECT_AFTER)
        if Config.LOGIN_REDIRECT_AFTER is not None
        else None,
    )
    payload_dict = request_payload.model_dump(mode="json")
    logger.debug(payload_dict)
    response = await client.post(
        f"{Config.AUTH_RELAY_URL}/issue_login_link",
        json=payload_dict,
    )
    try:
        response.raise_for_status()
    except HTTPStatusError as exc:
        logger.error(
            "Auth relay login link issuance failed: %s - %s",
            exc.response.status_code,
            exc.response.text,
        )
        raise HTTPException(
            status_code=502, detail="Failed to issue login link from auth relay"
        ) from exc

    try:
        return IssueLinkRes.model_validate(response.json())
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=502, detail="Invalid response from auth relay"
        ) from exc


def _kakao_identity_matches(
    *,
    db_user: "User",
    kakao_id: str,
    plusfriend_user_key: str | None,
) -> bool:
    """비교 규칙입니다.

    - 입력 plusfriend_user_key와 DB plusfriend_user_key가 둘 다 있으면 그것만으로 비교한다 (kakao_id 무시)
    - 그 외에는 kakao_id로 비교한다
    """
    if plusfriend_user_key and db_user.plusfriend_user_key:
        return db_user.plusfriend_user_key == plusfriend_user_key
    return db_user.kakao_id == kakao_id


async def map_keycloak_user(
    db: AsyncSession,
    kakao_id: str,
    keycloak_sub: str,  # OIDC/JWT의 sub (경계에서만 sub라고 부름)
    decrypted_access_token: str,
    decrypted_refresh_token: str,
    expires_in: int,
    refresh_expires_in: int,
    plusfriend_user_key: str | None = None,
) -> "User":
    """Keycloak 계정과 카카오 사용자를 매핑하고 토큰/만료 시각을 갱신합니다.

    충돌 규칙을 검증한 뒤 기존 사용자 레코드를 갱신하거나 신규 사용자를 생성합니다.

    Args:
        db (AsyncSession): 비동기 DB 세션.
        kakao_id (str): 카카오 사용자 식별자.
        keycloak_sub (str): Keycloak 토큰의 sub 값.
        decrypted_access_token (str): 평문 액세스 토큰.
        decrypted_refresh_token (str): 평문 리프레시 토큰.
        expires_in (int): 액세스 토큰 만료까지의 초 단위 값.
        refresh_expires_in (int): 리프레시 토큰 만료까지의 초 단위 값.
        plusfriend_user_key (str | None): 카카오 plusfriend 식별자.

    Returns:
        User: 갱신 또는 생성된 사용자 레코드.
    """
    encrypted_access_token = encrypt_token(decrypted_access_token)
    encrypted_refresh_token = encrypt_token(decrypted_refresh_token)
    access_expires_at = get_expiry_datetime(expires_in)
    refresh_expires_at = get_expiry_datetime(refresh_expires_in)

    try:
        async with db.begin():
            # 후보 조회: sub / kakao_id / (있으면) plusfriend_user_key
            conds = [User.keycloak_id == keycloak_sub, User.kakao_id == kakao_id]
            if plusfriend_user_key:
                conds.append(User.plusfriend_user_key == plusfriend_user_key)

            stmt = select(User).where(or_(*conds))
            result = await db.execute(stmt)
            rows = list(result.scalars().all())

            user_by_keycloak = next(
                (u for u in rows if u.keycloak_id == keycloak_sub), None
            )

            # "카카오 측 매칭"은 plusfriend_user_key 우선으로 잡는다(있으면)
            user_by_pf = (
                next(
                    (u for u in rows if u.plusfriend_user_key == plusfriend_user_key),
                    None,
                )
                if plusfriend_user_key
                else None
            )
            user_by_kakao = next((u for u in rows if u.kakao_id == kakao_id), None)

            user_by_kakao_identity = user_by_pf or user_by_kakao

            # 케이스 1) 둘 다 같은 레코드로 매칭 (정상)
            if (
                user_by_keycloak
                and user_by_kakao_identity
                and user_by_keycloak.id == user_by_kakao_identity.id
            ):
                u = user_by_keycloak
                u.access_token = encrypted_access_token
                u.refresh_token = encrypted_refresh_token
                u.access_token_expires_at = access_expires_at
                u.refresh_token_expires_at = refresh_expires_at
                # 식별자 값은 저장은 해두되, 비교는 위 규칙대로 처리
                u.kakao_id = kakao_id
                u.plusfriend_user_key = plusfriend_user_key
                await db.flush()
                await db.refresh(u)
                return u

            # 케이스 2) keycloak_sub는 있는데, "카카오 사용자"가 불일치
            if user_by_keycloak and not _kakao_identity_matches(
                db_user=user_by_keycloak,
                kakao_id=kakao_id,
                plusfriend_user_key=plusfriend_user_key,
            ):
                raise HTTPException(
                    status_code=409,
                    detail="해당 Keycloak 계정은 이미 다른 카카오 계정과 연결되어 있습니다.",
                )

            # 케이스 3) 카카오 사용자는 있는데, keycloak_sub가 불일치
            if (
                user_by_kakao_identity
                and user_by_kakao_identity.keycloak_id != keycloak_sub
            ):
                # 여기서도 ‘카카오 사용자’ 자체는 이미 user_by_kakao_identity로 결정된 상태
                raise HTTPException(
                    status_code=409,
                    detail="해당 카카오 계정은 이미 다른 Keycloak 계정과 연결되어 있습니다.",
                )

            # 케이스 4) 한쪽만 존재: 충돌이 아니라면 같은 사용자로 보고 붙여서 갱신
            existing_user = user_by_keycloak or user_by_kakao_identity
            if existing_user is None:
                raise HTTPException(
                    status_code=Config.HttpStatus.INTERNAL_SERVER_ERROR,
                    detail="User mapping state is inconsistent",
                )

            # (추가 안전장치) 혹시라도 sub가 있는데 카카오 불일치면 위에서 이미 차단됨
            existing_user.keycloak_id = keycloak_sub
            existing_user.kakao_id = kakao_id
            existing_user.plusfriend_user_key = plusfriend_user_key
            existing_user.access_token = encrypted_access_token
            existing_user.refresh_token = encrypted_refresh_token
            existing_user.access_token_expires_at = access_expires_at
            existing_user.refresh_token_expires_at = refresh_expires_at
            await db.flush()
            await db.refresh(existing_user)
            return existing_user

            # 케이스 5) 완전 신규
            new_user = User(
                keycloak_id=keycloak_sub,
                kakao_id=kakao_id,
                plusfriend_user_key=plusfriend_user_key,
                app_user_id=None,
                kakao_admin=False,
                access_token=encrypted_access_token,
                refresh_token=encrypted_refresh_token,
                access_token_expires_at=access_expires_at,
                refresh_token_expires_at=refresh_expires_at,
            )
            db.add(new_user)
            await db.flush()
            await db.refresh(new_user)
            return new_user

    except IntegrityError as exc:
        logger.error("IntegrityError while mapping user: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=409,
            detail="이미 다른 계정에 의해 매핑이 생성되었거나 충돌이 발생했습니다. 다시 시도해주세요.",
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Failed to map Keycloak user to Kakao user in DB: %s", exc, exc_info=True
        )
        raise HTTPException(
            status_code=Config.HttpStatus.INTERNAL_SERVER_ERROR,
            detail="Failed to map user in database",
        ) from exc
