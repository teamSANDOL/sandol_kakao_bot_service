"""데이터베이스 관련 모듈입니다.

비동기 SQLAlchemy를 사용하여 데이터베이스를 연결하고, 테이블을 생성합니다.
"""

from typing import Any

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import declarative_base

from app.config import Config

# 비동기 SQLAlchemy 엔진 생성
# SQLite 기본 busy timeout(5초)이 카카오 응답 제한(4초 예산)보다 길어,
# DB가 잠기면 응답이 지연된다. sqlite URL일 때만 2초로 줄인다.
_connect_args: dict[str, Any] = (
    {"timeout": 2} if Config.DATABASE_URL.startswith("sqlite") else {}
)
async_engine = create_async_engine(Config.DATABASE_URL, connect_args=_connect_args)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# Base 클래스 생성
Base = declarative_base()


async def init_db():
    """비동기로 데이터베이스 테이블을 생성합니다."""
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
