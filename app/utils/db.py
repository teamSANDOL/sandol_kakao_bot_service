"""이 모듈은 데이터베이스 세션과 사용자 인증 및 권한 확인을 위한 유틸리티 함수를 제공합니다."""

from app.database import AsyncSessionLocal


async def get_db():
    """비동기 데이터베이스 세션을 생성하고 반환합니다.

    Yields:
        AsyncSession: 비동기 데이터베이스 세션 객체
    """
    async with AsyncSessionLocal() as db:
        yield db
