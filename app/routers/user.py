"""카카오 챗봇 서비스의 사용자 관련 API를 정의합니다.

이 모듈은 사용자 생성, 조회, 목록 조회 및 삭제 기능을 제공합니다.
사용자 정보는 외부 사용자 서비스에서 가져오며, SQLAlchemy를 사용하여 데이터베이스와 상호작용합니다.
"""

from typing import Annotated

from sqlalchemy import select
from fastapi import APIRouter, Depends, HTTPException, Header, Request, status
from fastapi.responses import JSONResponse
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from kakao_chatbot import Payload
from kakao_chatbot.response import KakaoResponse

from app.config.config import Config, logger
from app.models.users import User
from app.schemas.users import IssueLinkRes, LoginCallbackReq
from app.utils.db import get_db
from app.utils.kakao import parse_payload
from app.utils.user import (
    generate_login_link,
    get_async_client,
    make_login_link_response,
)
from app.utils.auth_client import (
    mark_nonce_once,
    verify_relay_signature,
    verify_timestamp,
)
from app.services.authentication_service import (
    extract_keycloak_sub,
    get_user_info_from_keycloak,
    handle_token_exchange,
    map_keycloak_user,
    perform_token_exchange,
    process_keycloak_login,
)

user_router = APIRouter(prefix="/users", tags=["User"])


@user_router.get("/get_login_link")
async def get_login_link(
    payload: Annotated[Payload, Depends(parse_payload)],
    client: Annotated[AsyncClient, Depends(get_async_client)],
):
    """로그인 버튼을 제공합니다."""
    assert isinstance(payload.user_id, str)
    login_link_response: IssueLinkRes = await generate_login_link(payload, client)
    response: KakaoResponse = await make_login_link_response(login_link_response)
    return JSONResponse(content=response.get_dict())


@user_router.post(
    "/callback",
    summary="Auth Relay 로그인 콜백 처리",
    description="Auth Relay 콜백 검증, Keycloak 토큰 교환, 사용자 매핑/토큰 저장을 수행합니다.",
    status_code=Config.HttpStatus.OK,
    response_description="처리 성공 시 User ID 반환",
)
async def login_callback(
    data: LoginCallbackReq,  # Pydantic 모델로 요청 본문 받기
    db: Annotated[AsyncSession, Depends(get_db)],
    x_relay_signature: str | None = Header(default=None),
):
    """로그인 콜백을 처리하고 Token Exchange 및 사용자 정보 조회를 수행합니다."""
    try:
        # 1. 검증 (HMAC, Timestamp, Nonce)
        verify_relay_signature(x_relay_signature, data)
        verify_timestamp(data.ts)
        mark_nonce_once(data.nonce)
        logger.info("Relay callback signature, timestamp, nonce verified.")

        # --- 2. Token Exchange ---
        token_exchange_result = await handle_token_exchange(data.relay_access_token)
        try:
            access_token = token_exchange_result["access_token"] # 결과에서 값 추출
            refresh_token = token_exchange_result["refresh_token"]
            expires_in = token_exchange_result["expires_in"]
            refresh_expires_in = token_exchange_result["refresh_expires_in"]
        except KeyError as e:
            logger.error(
                f"Token Exchange result missing expected keys: {e}. "
                f"Result: {token_exchange_result.keys()}"
            )
            raise HTTPException(
                status_code=Config.HttpStatus.INTERNAL_SERVER_ERROR,
                detail="Token exchange response missing required fields. Check 'offline_access' scope.",
            ) from e
        finally:
            logger.info("Token Exchange completed successfully.")

        # --- 3. Keycloak Sub ID 추출 ---
        keycloak_sub = extract_keycloak_sub(access_token)
        logger.info(f"Extracted Keycloak sub ID: {keycloak_sub} for kakao_id: {data.chatbot_user_id}")

        # --- 4. DB 저장/매핑 ---
        user_map: User = await map_keycloak_user(
            db=db,
            kakao_id=data.chatbot_user_id,
            keycloak_sub=keycloak_sub,
            access_token=access_token, # 암호화되지 않은 토큰 전달
            refresh_token=refresh_token, # 암호화되지 않은 토큰 전달
            expires_in=expires_in,
            refresh_expires_in=refresh_expires_in,
            plusfriend_user_key=None # 필요 시 값 전달
        )
        logger.info(
            f"Keycloak login processed successfully for User ID: {user_map.id}, "
            f"kakao_id: {user_map.kakao_id} <-> keycloak_sub: {user_map.keycloak_sub}"
        )

        # --- 5. 성공 응답 반환 ---
        return {
            "status": "ok",
            "message": "Callback processed successfully",
            "user_map_id": user_map.id,
        }

    except HTTPException as e:
        logger.warning(f"Login callback failed with HTTPException: {e.status_code} - {e.detail}")
        return JSONResponse(content={"error": e.detail}, status_code=e.status_code)
    except Exception as e:
        logger.exception(f"Unexpected error during login callback for kakao_id: {data.chatbot_user_id}")
        return JSONResponse(
            content={"error": "internal_server_error", "detail": str(e)},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )