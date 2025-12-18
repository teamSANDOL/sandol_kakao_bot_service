"""Update user model for keycloak mapping

Revision ID: 360c2c6b25e1
Revises: 0597f17cc64d
Create Date: 2025-11-03 14:36:23.765798

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '360c2c6b25e1'
down_revision: Union[str, None] = '0597f17cc64d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """기존 User 테이블을 재사용하여 Keycloak 매핑 필드를 추가합니다."""
    op.rename_table("User", "user")

    with op.batch_alter_table("user") as batch_op:
        batch_op.add_column(
            sa.Column("keycloak_sub", sa.String(length=64), nullable=True)
        )
        batch_op.add_column(sa.Column("access_token", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("refresh_token", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column("access_token_expires_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("refresh_token_expires_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.create_unique_constraint("uq_keycloak_sub", ["keycloak_sub"])

    op.create_index("ix_user_keycloak_sub", "user", ["keycloak_sub"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_user_keycloak_sub", table_name="user")

    with op.batch_alter_table("user") as batch_op:
        batch_op.drop_constraint("uq_keycloak_sub", type_="unique")
        batch_op.drop_column("refresh_token_expires_at")
        batch_op.drop_column("access_token_expires_at")
        batch_op.drop_column("refresh_token")
        batch_op.drop_column("access_token")
        batch_op.drop_column("keycloak_sub")

    op.rename_table("user", "User")
