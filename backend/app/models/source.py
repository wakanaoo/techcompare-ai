"""Source(Web検索で取得した1件の情報源)のDBモデル。

Research 1 : N Sources の関係。Researchが削除されたら
紐づくSourceも一緒に削除する(ON DELETE CASCADE)。

contentはTavily APIが実際に取得した本文(生成AIの自由生成ではない)。
Evidence Viewerで表示する根拠本文の元データとして使う。
"""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.session import Base


class Source(Base):
    __tablename__ = "sources"

    id = Column(Integer, primary_key=True, index=True)
    research_id = Column(
        Integer,
        ForeignKey("researches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title = Column(String, nullable=False)
    url = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    retrieved_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    research = relationship("Research", back_populates="sources")
