"""Research(比較調査1件)のDBモデル。

status列はPostgreSQL固有のENUM型を使わず、シンプルな文字列 + CHECK制約にしている。
許容値そのものはPython/Pydantic側(app/schemas/research.py の ResearchStatus)で
Enumとして明確に定義し、こちらはあくまで「不正な値がDBに直接入らないための保険」。
"""

from sqlalchemy import CheckConstraint, Column, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.types import JSON

from app.db.session import Base

VALID_STATUSES = ("pending", "researching", "completed", "failed")
VALID_WINNERS = ("item_a", "item_b", "tie")

# PostgreSQLでは実際にJSONB(バイナリ格納・高速検索が可能なPostgreSQL独自の型)を使い、
# テスト用のSQLiteではJSON型にフォールバックする(with_variant)。
# 詳細はREADMEの「比較軸(criteria)の保存方法」を参照。
_CriteriaType = JSON().with_variant(JSONB(), "postgresql")


class Research(Base):
    __tablename__ = "researches"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'researching', 'completed', 'failed')",
            name="ck_researches_status",
        ),
        CheckConstraint(
            "recommendation_winner IS NULL OR recommendation_winner IN ('item_a', 'item_b', 'tie')",
            name="ck_researches_recommendation_winner",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    item_a = Column(String, nullable=False)
    item_b = Column(String, nullable=False)
    goal = Column(String, nullable=False)
    criteria = Column(_CriteriaType, nullable=False, default=list, server_default="[]")
    status = Column(String, nullable=False, server_default="pending")

    # 以下はResearch処理が completed / failed になった時点で埋まる(それまではNULL)。
    recommendation_winner = Column(String, nullable=True)
    recommendation_summary = Column(Text, nullable=True)
    recommendation_reason = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    comparisons = relationship(
        "Comparison", back_populates="research", cascade="all, delete-orphan"
    )
