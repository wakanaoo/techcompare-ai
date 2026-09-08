"""Research用のPydanticスキーマ(APIの入出力の型定義)。

DBモデル(app/models/research.py)とは別に定義することで、
「DBの内部構造」と「APIとして外に見せる形」を分離している。
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.criteria import Criterion


class ResearchStatus(str, Enum):
    """statusとして許される値をPython側で明確にするためのEnum。

    DB側はシンプルな文字列+CHECK制約(app/models/research.py参照)にとどめ、
    「どの値が正しいか」の一次情報はこちらに置く。
    """

    pending = "pending"
    researching = "researching"
    completed = "completed"
    failed = "failed"


class Winner(str, Enum):
    item_a = "item_a"
    item_b = "item_b"
    tie = "tie"


class ResearchCreate(BaseModel):
    """POST /research のリクエストボディ。"""

    item_a: str = Field(..., min_length=1, description="比較対象の技術A(例: FastAPI)")
    item_b: str = Field(..., min_length=1, description="比較対象の技術B(例: Django)")
    goal: str = Field(..., min_length=1, description="比較の目的・利用シーン")
    criteria: list[Criterion] = Field(
        ..., min_length=1, max_length=5, description="比較軸(1〜5個)"
    )


class ResearchRead(BaseModel):
    """POST /research と GET /research/{id} のレスポンス(polling用の軽量版)。"""

    id: int
    item_a: str
    item_b: str
    goal: str
    criteria: list[str]
    status: ResearchStatus
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    # SQLAlchemyのモデルインスタンスからそのまま変換できるようにする設定。
    model_config = ConfigDict(from_attributes=True)


class RecommendationRead(BaseModel):
    winner: Winner
    summary: str
    reason: str


class EvidenceRead(BaseModel):
    """Comparison Report画面の比較表に埋め込む、根拠の要約表示用。"""

    id: int
    source_id: int
    source_title: str
    source_url: str
    claim: str
    evidence_text: str


class ComparisonRead(BaseModel):
    id: int
    criterion: str
    criterion_label: str
    item_a_summary: str
    item_b_summary: str
    item_a_score: int
    item_b_score: int
    winner: Winner
    evidence: list[EvidenceRead] = []


class SourceRead(BaseModel):
    id: int
    title: str
    url: str

    model_config = ConfigDict(from_attributes=True)


class ResearchResultRead(BaseModel):
    """GET /research/{id}/result のレスポンス(completed時のみ)。"""

    research_id: int
    item_a: str
    item_b: str
    goal: str
    recommendation: RecommendationRead
    comparisons: list[ComparisonRead]
    sources: list[SourceRead]
