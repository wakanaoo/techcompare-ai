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


class EvidenceCitation(BaseModel):
    """根拠として選んだ、特定sourceの特定chunk 1件分の参照。

    Phase 5D: 根拠の粒度をSource単位からchunk単位に上げるための参照。
    LLMはsource_id/chunk_indexという「座標」を選ぶだけで、chunkの本文
    そのものは一切生成しない(生成させると存在しない引用文を作り出す
    リスクがあるため。README「Phase 3で追加したitem_a_source_ids」参照)。
    実際の本文はbackend側で、プロンプトに渡したchunk一覧から
    `chunk_index`を使って再取得する(research_runner.py参照)。
    """

    source_id: int = Field(..., description="根拠にした情報源のID。存在しないIDを作り出さないこと。")
    chunk_index: int = Field(
        ..., description="その情報源内で、根拠にした一節のchunk番号(提示された番号をそのまま使うこと)。"
    )


class ComparisonCriterionResult(BaseModel):
    """1つの比較軸についての結果。"""

    criterion: str = Field(..., description="比較軸の内部キー。指定されたキーをそのまま使うこと。")
    criterion_label: str = Field(..., description="比較軸の表示ラベル。指定されたラベルをそのまま使うこと。")
    item_a_summary: str = Field(..., description="この軸における技術Aの説明(日本語、2〜3文程度)")
    item_b_summary: str = Field(..., description="この軸における技術Bの説明(日本語、2〜3文程度)")
    item_a_score: int = Field(..., ge=1, le=5, description="技術Aのこの軸でのスコア(1〜5、5が最高)")
    item_b_score: int = Field(..., ge=1, le=5, description="技術Bのこの軸でのスコア(1〜5、5が最高)")
    winner: Winner = Field(..., description="この軸でどちらが優れているか")

    # NOTE: 根拠本文(evidence_text)自体はLLMに生成させない。
    # LLMが担うのは「提供した情報源のうち、どのchunkを根拠にしたか」の
    # 選択だけ。実際の根拠本文はbackend側でSource.contentから再計算した
    # chunkをそのまま使う(research_runner.py参照)。存在しないsource_id・
    # 範囲外のchunk_indexを挙げた場合はbackend側で無視する。
    item_a_citations: list[EvidenceCitation] = Field(
        default_factory=list,
        description=(
            "item_a_summaryの根拠にしたchunkの一覧({source_id, chunk_index})。"
            "提供された情報源に明確な記載がない場合は空リストにすること。"
            "存在しないsource_id・chunk_indexを作り出さないこと。"
        ),
    )
    item_b_citations: list[EvidenceCitation] = Field(
        default_factory=list,
        description=(
            "item_b_summaryの根拠にしたchunkの一覧({source_id, chunk_index})。"
            "提供された情報源に明確な記載がない場合は空リストにすること。"
            "存在しないsource_id・chunk_indexを作り出さないこと。"
        ),
    )


class RecommendationResult(BaseModel):
    """総合的な推奨結果。"""

    winner: Winner = Field(..., description="総合的にどちらを推奨するか")
    summary: str = Field(..., description="結論を1〜2文で(日本語)")
    reason: str = Field(..., description="なぜその結論に至ったかの理由(日本語)")


class ComparisonReportResult(BaseModel):
    """LLMから受け取るStructured Output全体の形。"""

    recommendation: RecommendationResult
    comparisons: list[ComparisonCriterionResult]


class CriterionSuggestionItem(BaseModel):
    """Suggest Points(POST /suggest-criteria)の提案1件。"""

    name: str = Field(..., description="追加/優先すべき比較ポイントの名前(日本語、短く)")
    reason: str = Field(..., description="このuse caseでなぜ重要かを1文程度で(日本語)")


class CriteriaSuggestionsResult(BaseModel):
    """Suggest PointsでLLMから受け取るStructured Output全体の形。"""

    suggestions: list[CriterionSuggestionItem]
