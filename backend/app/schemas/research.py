"""Research用のPydanticスキーマ(APIの入出力の型定義)。

DBモデル(app/models/research.py)とは別に定義することで、
「DBの内部構造」と「APIとして外に見せる形」を分離している。
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ResearchStatus(str, Enum):
    """statusとして許される値をPython側で明確にするためのEnum。

    DB側はシンプルな文字列+CHECK制約(app/models/research.py参照)にとどめ、
    「どの値が正しいか」の一次情報はこちらに置く。
    """

    pending = "pending"
    researching = "researching"
    completed = "completed"
    failed = "failed"


class ResearchCreate(BaseModel):
    """POST /research のリクエストボディ。"""

    item_a: str = Field(..., min_length=1, description="比較対象の技術A(例: FastAPI)")
    item_b: str = Field(..., min_length=1, description="比較対象の技術B(例: Django)")
    goal: str = Field(..., min_length=1, description="比較の目的・利用シーン")


class ResearchRead(BaseModel):
    """POST /research と GET /research/{id} のレスポンス。"""

    id: int
    item_a: str
    item_b: str
    goal: str
    status: ResearchStatus
    created_at: datetime
    updated_at: datetime

    # SQLAlchemyのモデルインスタンスからそのまま変換できるようにする設定。
    model_config = ConfigDict(from_attributes=True)
