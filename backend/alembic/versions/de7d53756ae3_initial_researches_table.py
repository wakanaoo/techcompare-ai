"""initial researches table

Phase 1で Base.metadata.create_all() によって作られていたスキーマを、
そのままmigrationとして記録したもの。新しい環境で `alembic upgrade head`
した場合にPhase 1と同じテーブルが作られる。

Revision ID: de7d53756ae3
Revises:
Create Date: 2026-09-08 13:40:09.087843

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'de7d53756ae3'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "researches",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("item_a", sa.String(), nullable=False),
        sa.Column("item_b", sa.String(), nullable=False),
        sa.Column("goal", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'researching', 'completed', 'failed')",
            name="ck_researches_status",
        ),
    )


def downgrade() -> None:
    op.drop_table("researches")
