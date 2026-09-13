"""add side to evidences

Revision ID: af3693a5c2dc
Revises: fec2d93e67a8
Create Date: 2026-09-11 14:20:31.847252

Evidence.side("item_a"/"item_b")を追加する。既存データを保ったまま
安全に列を追加するため、以下の順で実行する:

  1. nullableで`side`列を追加する
  2. 既存行をbackfillする(既存のResearch.item_a/item_bとEvidence.claimの
     前方一致だけを根拠にする。この判定はbackfill専用であり、
     research_runner.py側の新規データ作成では使わない)
  3. backfillしきれなかった行(=NULLのまま残った行)が無いことを確認する。
     1件でも残っていればRuntimeErrorでmigrationを失敗させる
     (推測で埋めない)。
  4. CHECK制約("item_a"/"item_b"のみ許可)を追加する
  5. NOT NULL化する
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'af3693a5c2dc'
down_revision: Union[str, Sequence[str], None] = 'fec2d93e67a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    connection = op.get_bind()

    # 1. nullableで列を追加する。
    op.add_column("evidences", sa.Column("side", sa.String(), nullable=True))

    # 2. 既存行をbackfillする。
    #    claimは research_runner.py が
    #    f"{side_label}の{criterion_label}について" という定型フォーマットで
    #    生成しており、side_labelはResearch.item_a/item_bそのもの
    #    (evaluation/run_eval.py::_evidence_side()と同じ判定方法)。
    #    starts_with()を使い、LIKEの特殊文字エスケープ問題を避ける。
    connection.execute(
        sa.text(
            """
            UPDATE evidences AS e
            SET side = CASE
                WHEN starts_with(e.claim, r.item_a || 'の') THEN 'item_a'
                WHEN starts_with(e.claim, r.item_b || 'の') THEN 'item_b'
                ELSE NULL
            END
            FROM comparisons AS c
            JOIN researches AS r ON r.id = c.research_id
            WHERE e.comparison_id = c.id
            """
        )
    )

    # 3. backfillしきれなかった行が無いことを確認する。
    unclassified_count = connection.execute(
        sa.text("SELECT COUNT(*) FROM evidences WHERE side IS NULL")
    ).scalar_one()
    if unclassified_count > 0:
        raise RuntimeError(
            f"{unclassified_count}件のEvidenceについて、claimからsideを"
            "backfillできませんでした。推測で埋めることはせず、migrationを"
            "失敗させています。該当データ・backfillロジックを確認してください。"
        )

    # 4. CHECK制約を追加する。
    op.create_check_constraint(
        "ck_evidences_side", "evidences", "side IN ('item_a', 'item_b')"
    )

    # 5. NOT NULL化する。
    op.alter_column("evidences", "side", nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("ck_evidences_side", "evidences", type_="check")
    op.drop_column("evidences", "side")
