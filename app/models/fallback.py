"""폴백 블록으로 떨어진 사용자 발화를 저장하는 테이블 모델 정의."""

import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _utcnow() -> datetime.datetime:
    """현재 시각을 UTC 타임존 포함 datetime으로 반환합니다."""
    return datetime.datetime.now(datetime.timezone.utc)


class FallbackUtterance(Base):
    """오픈빌더 폴백 블록으로 들어온 발화를 저장하는 테이블 모델.

    처리되지 못한 발화를 모아 추가할 블록/기능을 정하기 위한 분석용 로그입니다.

    Attributes:
        id (int): 레코드의 고유 기본 키 (자동 증가).
        utterance (str): 사용자 발화 (길이 상한 초과분은 잘림).
        kakao_user_id (str | None): userRequest.user.id. 없으면 None.
        block_id (str | None): 폴백 블록 ID.
        block_name (str | None): 폴백 블록 이름.
        bot_id (str | None): 봇 ID.
        params (dict | None): action.params.
        detail_params (dict | None): action.detailParams.
        flow (dict | None): payload의 flow (lastBlock, trigger 포함).
        trigger_type (str | None): flow.trigger.type. 분석용 인덱스 컬럼.
        trigger_referrer_block_id (str | None): flow.trigger.referrerBlock.id.
        trigger_referrer_block_name (str | None): flow.trigger.referrerBlock.name.
        raw_payload (dict | None): 토큰류와 callbackUrl을 제외한 원본 payload.
        created_at (datetime.datetime): 수집 시각 (UTC, 시간대 포함).
    """

    __tablename__ = "fallback_utterances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    utterance: Mapped[str] = mapped_column(String(500), index=True, nullable=False)
    kakao_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    block_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    block_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bot_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    params: Mapped[dict[str, Any] | None] = mapped_column(
        JSON(none_as_null=True), nullable=True
    )
    detail_params: Mapped[dict[str, Any] | None] = mapped_column(
        JSON(none_as_null=True), nullable=True
    )
    flow: Mapped[dict[str, Any] | None] = mapped_column(
        JSON(none_as_null=True), nullable=True
    )
    trigger_type: Mapped[str | None] = mapped_column(
        String(64), index=True, nullable=True
    )
    trigger_referrer_block_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    trigger_referrer_block_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(
        JSON(none_as_null=True), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False, default=_utcnow
    )
