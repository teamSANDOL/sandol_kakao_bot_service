"""카카오 챗봇 서비스의 사용자 관련 API를 정의합니다.

이 모듈은 사용자 생성, 조회, 목록 조회 및 삭제 기능을 제공합니다.
사용자 정보는 외부 사용자 서비스에서 가져오며, SQLAlchemy를 사용하여 데이터베이스와 상호작용합니다.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Header, status
from fastapi.responses import JSONResponse
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from kakao_chatbot import Payload
from kakao_chatbot.response import KakaoResponse

from app.config.config import Config, logger
from app.models.users import User
from app.schemas.auth import IssueLinkRes, LoginCallbackReq
from app.schemas.user import UserSchema
from app.services.auth_service import (
    generate_login_link,
    extract_keycloak_sub,
    mark_nonce_once,
    verify_relay_signature,
    verify_timestamp,
    map_keycloak_user,
)
from app.services.user_service import (
    get_current_user,
    get_user_info,
)
from app.utils.db import get_db
from app.utils.http import get_async_client
from app.utils.kakao import parse_payload
from app.utils.user import (
    make_login_link_response,
    make_user_info_response,
)

user_router = APIRouter(prefix="/users", tags=["User"])


@user_router.post("/get_login_link")
async def get_login_link(
    payload: Annotated[Payload, Depends(parse_payload)],
    client: Annotated[AsyncClient, Depends(get_async_client)],
):
    """로그인 버튼을 제공합니다."""
    login_link_response: IssueLinkRes = await generate_login_link(payload, client)
    response: KakaoResponse = await make_login_link_response(login_link_response)
    return JSONResponse(content=response.get_dict())


@user_router.post(
    "/callback",
    summary="Auth Relay 로그인 콜백 처리",
    description=(
        "Auth Relay 콜백 검증, 콜백 payload에 포함된 Keycloak 토큰 사용, "
        "사용자 매핑/토큰 저장을 수행합니다. (Token Exchange 호출 없음)"
    ),
    status_code=Config.HttpStatus.OK,
    response_description="처리 성공 시 User ID 반환",
)
async def login_callback(
    data: LoginCallbackReq,  # Pydantic 모델로 요청 본문 받기
    db: Annotated[AsyncSession, Depends(get_db)],
    x_relay_signature: str | None = Header(default=None),
):
    """로그인 콜백을 처리하고, 콜백에 포함된 토큰을 이용해 Keycloak 사용자 매핑을 수행합니다."""
    # 암호화여부를 명시적으로 나타내기 위해 변수명 변경
    decrypted_access_token = data.relay_access_token
    decrypted_refresh_token = data.offline_refresh_token
    logger.info(
        "Auth Relay login callback received: %s", data.model_dump()
    )  # TODO: Remove sensitive info in production(It may not be only here)

    try:
        # --- 1. 콜백 서명/타임스탬프/Nonce 검증 (위·변조 방지) ---
        verify_relay_signature(x_relay_signature, data)
        verify_timestamp(data.ts)
        mark_nonce_once(data.nonce)
        logger.info("Relay callback signature, timestamp, nonce verified.")

        # 필수 필드 검증: 콜백에 토큰이 없으면 구성 오류로 간주
        if not data.relay_access_token or not data.offline_refresh_token:
            logger.error(
                "Login callback payload missing required tokens: "
                "access_token=%s, refresh_token=%s",
                bool(data.relay_access_token),
                bool(data.offline_refresh_token),
            )  # TODO: Remove sensitive info in production(It may not be only here)
            raise HTTPException(
                status_code=Config.HttpStatus.INTERNAL_SERVER_ERROR,
                detail=(
                    "Login callback payload is missing required tokens. "
                    "Check Auth Relay / offline_access configuration."
                ),
            )

        logger.info(
            "Login callback tokens extracted successfully: "
            "expires_in=%s, refresh_expires_in=%s",
            data.expires_in,
            data.refresh_expires_in,
        )

        # --- 3. Keycloak Sub ID 추출 ---
        keycloak_sub = extract_keycloak_sub(decrypted_access_token)
        logger.info(
            "Extracted Keycloak sub ID: %s for kakao_id: %s",
            keycloak_sub,
            data.chatbot_user_id,
        )

        # --- 4. DB 저장/매핑 (기존 사용자 매핑 + 토큰 저장) ---
        user_map: User = await map_keycloak_user(
            db=db,
            kakao_id=data.chatbot_user_id,
            keycloak_sub=keycloak_sub,
            decrypted_access_token=decrypted_access_token,  # 암호화되지 않은 토큰 전달
            decrypted_refresh_token=decrypted_refresh_token,  # 암호화되지 않은 토큰 전달
            expires_in=data.expires_in,
            refresh_expires_in=data.refresh_expires_in,
            plusfriend_user_key=None,  # 필요 시 값 전달
        )
        logger.info(
            "Keycloak login processed successfully for User ID: %s, "
            "kakao_id: %s <-> keycloak_sub: %s",
            user_map.id,
            user_map.kakao_id,
            user_map.keycloak_id,
        )

        # --- 5. 성공 응답 반환 ---
        return {
            "status": "ok",
            "message": "Callback processed successfully",
            "user_map_id": user_map.id,
        }

    except HTTPException as e:
        # 비즈니스/검증 계층에서 발생한 HTTPException → 그대로 전달
        logger.warning(
            "Login callback failed with HTTPException: %s - %s",
            e.status_code,
            e.detail,
        )
        return JSONResponse(content={"error": e.detail}, status_code=e.status_code)

    except Exception as e:
        # 예기치 못한 오류 → 500으로 래핑
        logger.error(
            "Unexpected error during login callback for kakao_id: %s",
            data.chatbot_user_id,
        )
        return JSONResponse(
            content={"error": "internal_server_error", "detail": str(e)},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@user_router.post("/info", summary="내 정보 조회")
async def get_my_info(
    payload: Annotated[Payload, Depends(parse_payload)],
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    client: Annotated[AsyncClient, Depends(get_async_client)],
):
    """내 사용자 정보를 조회합니다."""
    user_info: UserSchema = await get_user_info(client, db, user)

    if not user_info:
        logger.warning("User not found: %s", payload.user_id)
        raise HTTPException(
            status_code=Config.HttpStatus.NOT_FOUND, detail="user_not_found"
        )
    logger.info("User info retrieved: %s", user_info.sub)

    response: KakaoResponse = await make_user_info_response(user_info)
    return JSONResponse(content=response.get_dict())
