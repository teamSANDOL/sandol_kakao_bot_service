"""create fallback_utterances table

Revision ID: a1c3f5e7b9d2
Revises: 74ec16c8761c
Create Date: 2026-10-10 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1c3f5e7b9d2'
down_revision: Union[str, None] = '74ec16c8761c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('fallback_utterances',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('utterance', sa.String(length=500), nullable=False),
    sa.Column('kakao_user_id', sa.String(length=64), nullable=True),
    sa.Column('block_id', sa.String(length=64), nullable=True),
    sa.Column('block_name', sa.String(length=255), nullable=True),
    sa.Column('bot_id', sa.String(length=64), nullable=True),
    sa.Column('params', sa.JSON(), nullable=True),
    sa.Column('detail_params', sa.JSON(), nullable=True),
    sa.Column('flow', sa.JSON(), nullable=True),
    sa.Column('trigger_type', sa.String(length=64), nullable=True),
    sa.Column('trigger_referrer_block_id', sa.String(length=64), nullable=True),
    sa.Column('trigger_referrer_block_name', sa.String(length=255), nullable=True),
    sa.Column('raw_payload', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_fallback_utterances_utterance'), 'fallback_utterances', ['utterance'], unique=False)
    op.create_index(op.f('ix_fallback_utterances_created_at'), 'fallback_utterances', ['created_at'], unique=False)
    op.create_index(op.f('ix_fallback_utterances_trigger_type'), 'fallback_utterances', ['trigger_type'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_fallback_utterances_trigger_type'), table_name='fallback_utterances')
    op.drop_index(op.f('ix_fallback_utterances_created_at'), table_name='fallback_utterances')
    op.drop_index(op.f('ix_fallback_utterances_utterance'), table_name='fallback_utterances')
    op.drop_table('fallback_utterances')
