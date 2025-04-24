"""사용자 관련 유틸리티 모듈

사용자 정보를 가져오거나 생성하는 기능을 포함합니다.
사용자 권한을 확인하는 기능도 포함되어 있습니다.
"""

from typing import Annotated, AsyncGenerator, Optional
from fastapi import Depends, HTTPException, Header
from httpx import AsyncClient
from kakao_chatbot import Payload
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.config import Config, logger
from app.models.users import User
from app.schemas.users import UserSchema
from app.utils.db import get_db
from app.utils.kakao import KakaoError, parse_payload
from app.utils.http import XUserIDClient


async def get_async_client(
    x_user_id: Optional[int] = Header(None),
) -> AsyncGenerator[XUserIDClient, None]:
    """비동기 HTTP 클라이언트를 생성하고 반환합니다.

    요청 헤더에 X-User-ID가 포함된 경우, 해당 값을 XUserIDClient에 설정하여 반환합니다.

    Args:
        x_user_id (Optional[int]): 요청 헤더에서 전달된 사용자 ID

    Yields:
        XUserIDClient: 사용자 ID를 포함할 수 있는 비동기 HTTP 클라이언트
    """
    async with XUserIDClient(user_id=x_user_id) as client:
        yield client


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
        result = await db.execute(select(User).where(User.app_user_id == app_user_id))
        user = result.scalar_one_or_none()

    # 3. kakao_id 검색
    if not user:
        result = await db.execute(select(User).where(User.kakao_id == kakao_id))
        user = result.scalar_one_or_none()

    # 없으면 새로 생성
    if not user:
        if plusfriend_user_key == "":
            plusfriend_user_key = None
        if app_user_id == "":
            app_user_id = None
        user = User(
            kakao_id=kakao_id,
            plusfriend_user_key=plusfriend_user_key,
            app_user_id=app_user_id,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    # 사용자 정보 자동 수정
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


async def get_current_user(
    payload: Annotated[Payload, Depends(parse_payload)],
    db: Annotated[AsyncSession, Depends(get_db)],
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
    if not payload.user_request.user.properties:
        plusfriend_user_key = None
        app_user_id = None
    else:
        plusfriend_user_key = payload.user_request.user.properties.plusfriend_user_key
        app_user_id = payload.user_request.user.properties.app_user_id
    return await get_or_create_user(
        kakao_id,
        db,
        plusfriend_user_key=plusfriend_user_key,
        app_user_id=app_user_id,
    )


async def get_current_user_by_header(
    db: Annotated[AsyncSession, Depends(get_db)],
    x_user_id: int = Header(None),
) -> User:
    """X-User-ID 헤더를 가져와 비동기 방식으로 User 객체를 반환합니다.

    Args:
        x_user_id (int): 요청 헤더에서 가져온 사용자 ID
        db (AsyncSession): 비동기 데이터베이스 세션

    Returns:
        User: 데이터베이스에서 조회된 사용자 객체

    Raises:
        HTTPException: X-User-ID 헤더가 없거나 사용자가 존재하지 않는 경우
    """
    if x_user_id is None:
        raise HTTPException(
            status_code=Config.HttpStatus.UNAUTHORIZED,
            detail="X-User-ID 헤더가 필요합니다.",
        )

    result = await db.execute(select(User).where(User.id == x_user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=Config.HttpStatus.NOT_FOUND,
            detail="사용자를 찾을 수 없습니다.",
        )

    return user


async def get_user_info(
    user_id: int,
    client: AsyncClient,
) -> UserSchema:
    """사용자 정보를 가져와 UserSchema 객체를 반환합니다.

    Args:
        user_id (int): 사용자 ID
        client (AsyncClient): 비동기 HTTP 클라이언트

    Returns:
        UserSchema: 사용자 정보가 담긴 스키마 객체

    Raises:
        HTTPException: 사용자 정보 조회 실패 시
    """
    response = await client.get(f"{Config.USER_SERVICE_URL}/api/users/{user_id}/")
    try:
        response.raise_for_status()
    except Exception as e:
        logger.warning(f"User service에서 사용자 정보를 가져오는 중 오류 발생: {e}")
        logger.warning("반환 값 : %s", response.json())
        if response.status_code == Config.HttpStatus.NOT_FOUND:
            raise HTTPException(
                status_code=Config.HttpStatus.NOT_FOUND,
                detail="사용자를 찾을 수 없습니다.",
            ) from e
        if response.status_code == Config.HttpStatus.UNAUTHORIZED:
            raise HTTPException(
                status_code=Config.HttpStatus.UNAUTHORIZED,
                detail="권한이 없습니다.",
            ) from e
        if response.status_code == Config.HttpStatus.FORBIDDEN:
            raise HTTPException(
                status_code=Config.HttpStatus.FORBIDDEN,
                detail="권한이 없습니다.",
            ) from e
        if response.status_code == Config.HttpStatus.BAD_REQUEST:
            raise HTTPException(
                status_code=Config.HttpStatus.BAD_REQUEST,
                detail="잘못된 요청입니다.",
            ) from e
        raise HTTPException(
            status_code=Config.HttpStatus.INTERNAL_SERVER_ERROR, detail=str(e)
        ) from e
    return UserSchema.model_validate(response.json(), strict=False)


async def is_global_admin(user_id: int, client: AsyncClient) -> bool:
    """User API 서버에 요청하여 global_admin 여부 확인"""
    if Config.debug:
        return user_id == 1
    response = await client.get(
        f"{Config.USER_SERVICE_URL}/api/users/{user_id}/is_global_admin/"
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
    kakao_request: bool = True,
) -> bool:
    """사용자가 관리자 권한을 가지고 있는지 확인합니다.

    Args:
        user (UserSchema): 사용자 정보가 담긴 스키마 객체
        client (AsyncClient): 비동기 HTTP 클라이언트
        kakao_request (bool): 카카오 요청 여부 (기본값: True)

    Returns:
        bool: 관리자 권한 여부

    Raises:
        HTTPException: 사용자가 관리자 권한이 없는 경우
    """
    if user.kakao_admin or await is_global_admin(user.id, client):
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
    client: Annotated[AsyncClient, Depends(get_async_client)],
    payload: Annotated[Payload, Depends(parse_payload)],
) -> User:
    """현재 사용자가 관리자 권한을 가지고 있는지 확인하고 UserSchema 객체를 반환합니다.

    Args:
        payload (Payload): 요청 페이로드
        db (AsyncSession): 비동기 데이터베이스 세션
        client (AsyncClient): 비동기 HTTP 클라이언트

    Returns:
        User: 관리자 권한이 확인된 사용자 DB 객체

    Raises:
        HTTPException: 사용자 정보 조회 실패 시
    """
    user = await get_current_user(payload, db)
    await check_admin_user(user, client)
    return user


async def get_admin_user_by_header(
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
    user = await get_current_user_by_header(db, x_user_id)
    await check_admin_user(user, client)
    return user
