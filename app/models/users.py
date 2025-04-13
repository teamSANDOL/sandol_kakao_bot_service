"""이 모듈은 사용자 정보를 저장하는 User 클래스를 정의합니다."""

from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Integer, Boolean, String

from app.database import Base


class User(Base):
    """사용자 정보를 저장하는 클래스

    Attributes:
        __tablename__ (str): 데이터베이스 테이블 이름
        id (int): 내부 고유 사용자 ID
        kakao_id (str): 카카오톡에서 제공하는 사용자 ID
        plusfriend_user_key (str): 플러스친구 사용자 고유키
        app_user_id (str): OpenBuilder의 사용자 ID (앱 전용)
        kakao_admin (bool): 카카오 관리자 여부
    """

    __tablename__ = "User"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kakao_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False
    )  # payload.user_id와 대응
    plusfriend_user_key: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=True
    )
    app_user_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=True)
    kakao_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
