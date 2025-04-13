from typing import Annotated, AsyncGenerator

from fastapi import Depends
from kakao_chatbot import Payload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.users import User
from app.utils.db import get_db
from app.utils.http import XUserIDClient
from app.utils.kakao import parse_payload
from app.utils.user import get_or_create_user


async def get_xuser_client_by_payload(
    payload: Annotated[Payload, Depends(parse_payload)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AsyncGenerator[XUserIDClient, None]:
    """Payload로부터 kakao_id를 추출 → DB 조회 → user_id 기반 HTTP 클라이언트 반환"""
    kakao_id = payload.user_request.user.id
    user: User = await get_or_create_user(kakao_id, db)
    async with XUserIDClient(user_id=user.id) as client:
        yield client
