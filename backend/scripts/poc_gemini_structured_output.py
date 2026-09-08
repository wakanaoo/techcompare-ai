"""Gemini APIで「ネストしたPydantic Structured Output」が動くかを検証するPoC。

目的:
  Anthropic Claude APIからGoogle Gemini APIへ切り替える前に、本実装
  (app/services/llm_schemas.py の ComparisonReportResult)と同じ形の
  「ネストしたPydanticモデル」を google-genai SDK の response_schema に
  渡した場合に、期待通り動作するかを実際に1回だけAPIを呼んで確認する。

  google-genai SDKには、ネストしたPydantic BaseModelをresponse_schemaに
  渡すとうまく変換できないケースが報告されている(GitHub issue #60, #699)。
  本実装(app/services/llm_client.py, app/services/llm_schemas.py)を書き換える
  前に、ここで問題がないか確認しておく。

実行方法:
    cd backend
    source venv/bin/activate
    export GEMINI_API_KEY=...   # https://aistudio.google.com/apikey で発行
    python scripts/poc_gemini_structured_output.py

このスクリプトはAPIを1回だけ呼び出す(無料枠の範囲内)。
"""

from enum import Enum

from google import genai
from google.genai import types
from pydantic import BaseModel, Field


class Winner(str, Enum):
    item_a = "item_a"
    item_b = "item_b"
    tie = "tie"


class ComparisonCriterionResult(BaseModel):
    criterion: str
    criterion_label: str
    item_a_summary: str
    item_b_summary: str
    item_a_score: int = Field(ge=1, le=5)
    item_b_score: int = Field(ge=1, le=5)
    winner: Winner


class RecommendationResult(BaseModel):
    winner: Winner
    summary: str
    reason: str


class ComparisonReportResult(BaseModel):
    """本実装(app/services/llm_schemas.py)と同じ、ネストした構造。"""

    recommendation: RecommendationResult
    comparisons: list[ComparisonCriterionResult]


PROMPT = """FastAPIとDjangoを、「開発速度」という1つの比較軸だけで比較してください。
スコアは1〜5の整数、winnerはitem_a/item_b/tieのいずれかで答えてください。
criterionには"development_speed"、criterion_labelには"開発速度"を入れてください。"""


def main() -> None:
    # GEMINI_API_KEY(またはGOOGLE_API_KEY)環境変数から自動でキーを取得する。
    client = genai.Client()

    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents=PROMPT,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ComparisonReportResult,
        ),
    )

    print("=== raw text ===")
    print(response.text)

    result = response.parsed
    print("\n=== parsed ===")
    print(f"type: {type(result)}")
    print(result)

    if not isinstance(result, ComparisonReportResult):
        raise SystemExit(
            "PoC失敗: response.parsedがComparisonReportResultとして返ってきませんでした。"
            "ネストしたPydanticモデルの扱いに問題がある可能性があります。"
        )

    print("\nPoC成功: ネストしたPydanticモデルがそのままresponse.parsedで返ってきました。")


if __name__ == "__main__":
    main()
