"""카카오 사용자 정보와 Keycloak 사용자 정보 및 토큰을 매핑하는 테이블 모델 정의."""

import datetime

from sqlalchemy import (
    Integer,
    String,
    Text,
    DateTime,
    Boolean,  # Boolean 추가
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

# Base는 app/database.py 등에서 임포트해야 합니다.
from app.database import Base


class User(Base):
    """카카오 사용자 정보와 Keycloak 사용자 정보 및 토큰을 매핑하는 테이블 모델.

    이 클래스는 SQLAlchemy의 선언적 Base를 상속받아 `user_map` 테이블과 매핑됩니다.
    카카오톡 챗봇 사용자의 고유 ID와 Keycloak 인증 후 발급받은 사용자 ID(`sub`),
    그리고 Keycloak 토큰(Access Token, Refresh Token) 및 관련 정보를 저장합니다.

    Attributes:
        id (int): 레코드의 고유 기본 키 (자동 증가).
        keycloak_id (str): Keycloak 사용자의 고유 식별자 ('id' 클레임). 고유해야 함.
        kakao_id (str): 카카오톡 사용자의 고유 ID (payload.user_id). 고유해야 함.
        plusfriend_user_key (str | None): 카카오톡 플러스친구 사용자 키 (선택 사항). 고유해야 함.
        app_user_id (str | None): 카카오톡 OpenBuilder 앱 사용자 ID (선택 사항). 고유해야 함.
        access_token (str | None): 암호화된 Keycloak Access Token (JWT).
        refresh_token (str | None): 암호화된 Keycloak Refresh Token.
        access_token_expires_at (datetime.datetime | None): Access Token의 만료 시각 (시간대 포함).
        refresh_token_expires_at (datetime.datetime | None): Refresh Token의 만료 시각 (시간대 포함).
        kakao_admin (bool): 해당 카카오 사용자가 서비스 내 관리자 권한을 가졌는지 여부.
    """

    __tablename__ = "user"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    keycloak_id: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    kakao_id: Mapped[str] = mapped_column(
        String(64), index=True, unique=True, nullable=False
    )
    plusfriend_user_key: Mapped[str | None] = mapped_column(
        String(64), unique=True, nullable=True
    )
    access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    access_token_expires_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    refresh_token_expires_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # --- User 모델에서 가져온 필드 ---
    app_user_id: Mapped[str | None] = mapped_column(  # Nullable로 변경 (User 모델 참조)
        String(64), unique=True, nullable=True
    )
    kakao_admin: Mapped[bool] = mapped_column(  # User 모델 참조
        Boolean, nullable=False, default=False
    )

    # --- 테이블 제약 조건 ---
    __table_args__ = (
        UniqueConstraint("keycloak_id", name="uq_keycloak_id"),
        # 필요 시 다른 Unique Constraint 추가 가능 (예: kakao_id, app_user_id 등)
        UniqueConstraint("kakao_id", name="uq_kakao_id"),
        UniqueConstraint("app_user_id", name="uq_app_user_id"),
    )

    def __repr__(self) -> str:
        """디버깅용 사용자 모델 문자열 표현을 반환합니다."""
        return (
            f"<User(id={self.id}, kakao_id='{self.kakao_id}', "
            f"keycloak_id='{self.keycloak_id}', "
            f"app_user_id='{self.app_user_id}', "
            f"plusfriend_user_key='{self.plusfriend_user_key}', "
            f"kakao_admin={self.kakao_admin})>"
        )
