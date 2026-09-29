"""Suggest Points(POST /suggest-criteria)用のPydanticスキーマ(API入出力)。

このモジュールのモデルはLLM Structured Output用のスキーマ
(app/services/llm_schemas.py::CriterionSuggestionItem等)とは別物。
既存のComparisonReportResult/ComparisonReadの分離方針(README参照)と同様、
「LLMに何の形で返してもらうか」と「APIとして外に見せる形」を分離している。
"""

from pydantic import BaseModel, Field


class SuggestCriteriaRequest(BaseModel):
    """POST /suggest-criteria のリクエストボディ。"""

    item_a: str = Field(..., min_length=1, description="比較対象の技術A")
    item_b: str = Field(..., min_length=1, description="比較対象の技術B")
    goal: str = Field(..., min_length=1, description="比較の目的・利用シーン")
    existing_criteria: list[str] = Field(
        default_factory=list,
        description=(
            "その時点で表示・選択対象になっているBase Points(比較ポイント)。"
            "Geminiがこれと重複する提案を避けるための参考情報として渡す。"
        ),
    )


class CriterionSuggestion(BaseModel):
    name: str
    reason: str


class SuggestCriteriaResponse(BaseModel):
    """POST /suggest-criteria のレスポンス。"""

    suggestions: list[CriterionSuggestion]
