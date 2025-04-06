from typing import AsyncGenerator
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from kakao_chatbot import Payload
from app.models.user import User
from app.utils.db import get_db, get_or_create_user
from app.utils.kakao import parse_payload
from app.utils.http import XUserIDClient


async def get_xuser_client_by_payload(
    payload: Payload = Depends(parse_payload),
    db: AsyncSession = Depends(get_db),
) -> AsyncGenerator[XUserIDClient, None]:
    """Payload로부터 kakao_id를 추출 → DB 조회 → user_id 기반 HTTP 클라이언트 반환"""
    kakao_id = payload.user_request.user.id
    user: User = await get_or_create_user(kakao_id, db)
    async with XUserIDClient(user_id=user.id) as client:
        yield client
