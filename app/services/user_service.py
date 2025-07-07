from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.config import Config
from app.models.users import User
from app.schemas.users import UserCreate


async def create_user_process(user_in: UserCreate, db: AsyncSession) -> User:
    """사용자를 생성하는 비즈니스 로직.

    Args:
        user_in (UserCreate): 사용자 생성에 필요한 정보.
        db (AsyncSession): 비동기 데이터베이스 세션.

    Raises:
        HTTPException: 사용자 정보가 외부 서비스에 존재하지 않거나,
                          이미 존재하는 경우 오류 발생.

    Returns:
        User: 생성된 사용자 객체.
    """
    existing_user = await db.scalar(select(User).where(User.id == user_in.id))
    if existing_user:
        raise HTTPException(
            status_code=Config.HttpStatus.CONFLICT,
            detail="User already exists",
        )

    user = User(**user_in.model_dump())
    db.add(user)
    try:
        await db.commit()
    except SQLAlchemyError as e:
        await db.rollback()
        raise HTTPException(
            status_code=Config.HttpStatus.INTERNAL_SERVER_ERROR,
            detail="DB Commit Failure",
        ) from e
    await db.refresh(user)
    return user
