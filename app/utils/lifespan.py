"""DB의 meal_type 테이블을 meal_types.json과 동기화"""

import traceback

from sqlalchemy.exc import IntegrityError
from sqlalchemy.future import select

from app.database import AsyncSessionLocal
from app.config import Config, logger
from app.models.users import User


async def set_service_account():
    """서비스 계정 설정

    서비스 계정이 설정되어 있지 않은 경우, 기본 서비스 계정을 설정합니다.
    """
    async with AsyncSessionLocal() as db:
        try:
            # 서비스 계정이 이미 존재하는지 확인
            result = await db.execute(select(User).where(User.id == Config.SERVICE_ID))
            service_account = result.scalar_one_or_none()
            if not service_account:
                # 서비스 계정 생성
                service_account = User(
                    id=Config.SERVICE_ID,
                    kakao_id="__SERVICE__",
                    app_user_id="__SERVICE__",
                    plusfriend_user_key="__SERVICE__",
                    kakao_admin=True,
                )
                db.add(service_account)
                await db.commit()
                logger.info("서비스 계정이 생성되었습니다.")
            else:
                logger.info("서비스 계정이 이미 존재합니다.")

        except IntegrityError:
            message = traceback.format_exc()
            logger.debug("Error details: %s", message)
            logger.warning("중복된 서비스 계정이 감지되었습니다.")
            await db.rollback()
            logger.debug("DB 롤백 완료")
