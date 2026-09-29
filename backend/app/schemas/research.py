"""Research用のPydanticスキーマ(APIの入出力の型定義)。

DBモデル(app/models/research.py)とは別に定義することで、
「DBの内部構造」と「APIとして外に見せる形」を分離している。
"""

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.criteria import canonical_key_for, validate_criterion_text


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
    criteria: list[str] = Field(
        ...,
        min_length=1,
        max_length=5,
        description=(
            "比較軸(1〜5個)。固定候補のキー、またはユーザーの自由入力文字列。"
            "各要素はtrim後1〜40文字、改行・制御文字は不可、重複不可"
            "(trim後・大文字小文字を無視して判定)。"
        ),
    )

    @field_validator("criteria")
    @classmethod
    def _validate_criteria(cls, value: list[str]) -> list[str]:
        """各criterionをtrimし、長さ・禁止文字・重複を検証する。

        固定候補(Criterion)かどうかは問わない(自由入力を許可するため)。
        重複判定はcanonical_key_for()による正規化キーで行う。これにより、
        固定候補のkey("cost")とlabel("コスト")のように表記は異なるが
        意味的には同じcriterionも重複として扱う(既存の固定key↔label対応
        だけが対象。類義語判定やLLMによる意味判定はしない)。

        trim・長さ・制御文字の検証自体はapp/schemas/criteria.py::
        validate_criterion_text()に集約している(Phase 5CのAI提案
        (POST /suggest-criteria)側のdefense-in-depth検証と同じルールを
        共有するため)。
        """
        normalized: list[str] = []
        seen: set[str] = set()

        for raw in value:
            trimmed = validate_criterion_text(raw)
            dedupe_key = canonical_key_for(trimmed)
            if dedupe_key in seen:
                raise ValueError(f"比較軸が重複しています: {trimmed}")
            seen.add(dedupe_key)
            normalized.append(trimmed)

        return normalized


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
    # このEvidenceがitem_a/item_bどちらの主張を裏付けるものかを示す。
    # frontend側でこの値を使って、item_a/item_bそれぞれのsummary直下に
    # 対応するEvidenceだけを表示する(evidence配列自体はitem_a/item_b
    # 混在のまま、side単位で分割はしない)。
    side: Literal["item_a", "item_b"]
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
