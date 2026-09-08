"""Comparison(1つの比較軸についての比較結果)のDBモデル。

Research 1 : N Comparisons の関係。Research 1件が削除されたら
紐づくComparisonも一緒に削除する(ON DELETE CASCADE)。
"""

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.session import Base


class Comparison(Base):
    __tablename__ = "comparisons"
    __table_args__ = (
        CheckConstraint(
            "winner IN ('item_a', 'item_b', 'tie')", name="ck_comparisons_winner"
        ),
        CheckConstraint(
            "item_a_score BETWEEN 1 AND 5", name="ck_comparisons_item_a_score_range"
        ),
        CheckConstraint(
            "item_b_score BETWEEN 1 AND 5", name="ck_comparisons_item_b_score_range"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    research_id = Column(
        Integer,
        ForeignKey("researches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    criterion = Column(String, nullable=False)
    criterion_label = Column(String, nullable=False)
    item_a_summary = Column(Text, nullable=False)
    item_b_summary = Column(Text, nullable=False)
    item_a_score = Column(Integer, nullable=False)
    item_b_score = Column(Integer, nullable=False)
    winner = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    research = relationship("Research", back_populates="comparisons")
