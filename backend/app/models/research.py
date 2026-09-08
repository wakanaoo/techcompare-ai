"""Research(比較調査1件)のDBモデル。

status列はPostgreSQL固有のENUM型を使わず、シンプルな文字列 + CHECK制約にしている。
許容値そのものはPython/Pydantic側(app/schemas/research.py の ResearchStatus)で
Enumとして明確に定義し、こちらはあくまで「不正な値がDBに直接入らないための保険」。
"""

from sqlalchemy import CheckConstraint, Column, DateTime, Integer, String
from sqlalchemy.sql import func

from app.db.session import Base

VALID_STATUSES = ("pending", "researching", "completed", "failed")


class Research(Base):
    __tablename__ = "researches"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'researching', 'completed', 'failed')",
            name="ck_researches_status",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    item_a = Column(String, nullable=False)
    item_b = Column(String, nullable=False)
    goal = Column(String, nullable=False)
    status = Column(String, nullable=False, server_default="pending")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # NOTE: recommendation / error_message は将来(比較生成・Research実行の
    # フェーズ)で使う列だが、Phase 1では書き込む処理がまだ存在しないため
    # 今は追加しない。実際に使うタイミングでmigrationとして追加する
    # (理由はREADMEの「recommendation/error_messageを今入れない理由」を参照)。
