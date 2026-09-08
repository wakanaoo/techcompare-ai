"""LLMのStructured Output(client.messages.parse)で使うPydanticスキーマ。

このモジュールのモデルはAPIの入出力スキーマ(app/schemas/)とは別物。
「LLMに何の形で返してもらうか」だけを定義する。
"""

from enum import Enum

from pydantic import BaseModel, Field


class Winner(str, Enum):
    item_a = "item_a"
    item_b = "item_b"
    tie = "tie"


class ComparisonCriterionResult(BaseModel):
    """1つの比較軸についての結果。"""

    criterion: str = Field(..., description="比較軸の内部キー。指定されたキーをそのまま使うこと。")
    criterion_label: str = Field(..., description="比較軸の表示ラベル。指定されたラベルをそのまま使うこと。")
    item_a_summary: str = Field(..., description="この軸における技術Aの説明(日本語、2〜3文程度)")
    item_b_summary: str = Field(..., description="この軸における技術Bの説明(日本語、2〜3文程度)")
    item_a_score: int = Field(..., ge=1, le=5, description="技術Aのこの軸でのスコア(1〜5、5が最高)")
    item_b_score: int = Field(..., ge=1, le=5, description="技術Bのこの軸でのスコア(1〜5、5が最高)")
    winner: Winner = Field(..., description="この軸でどちらが優れているか")


class RecommendationResult(BaseModel):
    """総合的な推奨結果。"""

    winner: Winner = Field(..., description="総合的にどちらを推奨するか")
    summary: str = Field(..., description="結論を1〜2文で(日本語)")
    reason: str = Field(..., description="なぜその結論に至ったかの理由(日本語)")


class ComparisonReportResult(BaseModel):
    """LLMから受け取るStructured Output全体の形。"""

    recommendation: RecommendationResult
    comparisons: list[ComparisonCriterionResult]
