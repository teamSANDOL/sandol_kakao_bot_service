"""이 모듈은 데이터베이스 세션과 사용자 인증 및 권한 확인을 위한 유틸리티 함수를 제공합니다."""

from typing import Annotated

from fastapi import Depends, Header, HTTPException
from httpx import AsyncClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from kakao_chatbot import Payload

from app.config import Config
from app.database import AsyncSessionLocal, 
from app.models.user import User  # User 모델이 models 디렉토리에 있다고 가정
from app.utils.http import get_async_client
from app.utils.kakao import parse_payload


async def get_db():
    """비동기 데이터베이스 세션을 생성하고 반환합니다.

    Yields:
        AsyncSession: 비동기 데이터베이스 세션 객체
    """
    async with AsyncSessionLocal() as db:
        yield db


async def get_or_create_user(
    kakao_id: str,
    db: AsyncSession,
    plusfriend_user_key: str | None = None,
    app_user_id: str | None = None,
) -> User:
    """사용자를 ID 우선순위에 따라 검색하고 없으면 새로 생성합니다.

    우선순위: 1. plusfriend_user_key → 2. app_user_id → 3. kakao_id
    """

    user = None

    # 1. plusfriend_user_key 우선 검색
    if plusfriend_user_key:
        result = await db.execute(
            select(User).where(User.plusfriend_user_key == plusfriend_user_key)
        )
        user = result.scalar_one_or_none()

    # 2. app_user_id 검색
    if not user and app_user_id:
        result = await db.execute(
            select(User).where(User.app_user_id == app_user_id)
        )
        user = result.scalar_one_or_none()

    # 3. kakao_id 검색
    if not user:
        result = await db.execute(select(User).where(User.kakao_id == kakao_id))
        user = result.scalar_one_or_none()

    # 없으면 새로 생성
    if not user:
        user = User(
            kakao_id=kakao_id,
            plusfriend_user_key=plusfriend_user_key,
            app_user_id=app_user_id,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    return user


async def get_current_user(
    payload: Payload = Depends(parse_payload),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Payload로부터 kakao_id를 추출 → DB 조회 → 사용자 객체 반환

    Args:
        payload (Payload): 요청 페이로드
        db (AsyncSession): 비동기 데이터베이스 세션
    Returns:
        User: 사용자 객체
    Raises:
        HTTPException: 사용자 정보 조회 실패 시
    """
    kakao_id = payload.user_request.user.id
    plusfriend_user_key = payload.user_request.user.properties.plusfriend_user_key
    app_user_id = payload.user_request.user.properties.app_user_id
    return await get_or_create_user(
        kakao_id,
        db,
        plusfriend_user_key=plusfriend_user_key,
        app_user_id=app_user_id,
    )

async def get_user_info(
    user_id: int,
    client: AsyncClient,
):
    """사용자 정보를 가져와 UserSchema 객체를 반환합니다.

    Args:
        user_id (int): 사용자 ID
        client (AsyncClient): 비동기 HTTP 클라이언트

    Returns:
        UserSchema: 사용자 정보가 담긴 스키마 객체

    Raises:
        HTTPException: 사용자 정보 조회 실패 시
    """

async def is_global_admin(user_id: int, client: AsyncClient) -> bool:
    """User API 서버에 요청하여 global_admin 여부 확인"""
    if Config.debug:
        return user_id == 1
    response = await client.get(
        f"{Config.USER_SERVICE_URL}user/api/users/{user_id}/is_global_admin/"
    )

    try:
        response.raise_for_status()
    except Exception as e:
        raise HTTPException(
            status_code=Config.HttpStatus.INTERNAL_SERVER_ERROR, detail=str(e)
        ) from e

    return response.json().get("is_global_admin", False)


async def check_admin_user(
    user: User,
    client: AsyncClient,
) -> bool:
    """사용자가 관리자 권한을 가지고 있는지 확인합니다.

    Args:
        user (UserSchema): 사용자 정보가 담긴 스키마 객체
        client (AsyncClient): 비동기 HTTP

    Returns:
        bool: 관리자 권한 여부

    Raises:
        HTTPException: 사용자가 관리자 권한이 없는 경우
    """
    if user.kakao_admin or await is_global_admin(user.id, client):
        return True
    raise HTTPException(
        status_code=Config.HttpStatus.FORBIDDEN, detail="관리자 권한이 필요합니다."
    )


async def get_admin_user(
    db: Annotated[AsyncSession, Depends(get_db)],
    client: Annotated[AsyncClient, Depends(get_async_client)],
    x_user_id: int = Header(None),
) -> User:
    """현재 사용자가 관리자 권한을 가지고 있는지 확인하고 UserSchema 객체를 반환합니다.

    Args:
        x_user_id (int): 요청 헤더에서 가져온 사용자 ID
        db (AsyncSession): 비동기 데이터베이스 세션
        client (AsyncClient): 비동기 HTTP 클라이언트

    Returns:
        User: 관리자 권한이 확인된 사용자 DB 객체

    Raises:
        HTTPException: X-User-ID 헤더가 없거나 사용자가 존재하지 않는 경우
    """
    user = await get_current_user(db, client, x_user_id)
    await check_admin_user(user, client)
    return user
