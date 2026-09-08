"""Evidence(1つのComparisonの主張を裏付ける根拠)のDBモデル。

Comparison 1 : N Evidences の関係。

重要な設計上の制約(README「Evidenceの根拠本文について」参照):
- claim / evidence_text はLLMの自由生成ではなく、backend側で組み立てる。
  claimは "item_aの{criterion_label}について" のような定型文、
  evidence_textはSource.contentをそのまま複製したもの。
  LLMが担うのは「どのsource_idを根拠にしたか」の選択だけで、
  根拠本文そのものを生成させない(存在しない引用文の捏造を防ぐため)。
"""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.session import Base


class Evidence(Base):
    __tablename__ = "evidences"

    id = Column(Integer, primary_key=True, index=True)
    comparison_id = Column(
        Integer,
        ForeignKey("comparisons.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_id = Column(
        Integer,
        ForeignKey("sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    claim = Column(Text, nullable=False)
    evidence_text = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    comparison = relationship("Comparison", back_populates="evidences")
    source = relationship("Source")
