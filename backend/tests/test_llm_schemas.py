"""LLMのStructured Output(ComparisonReportResult)のスキーマ検証テスト。

実際のLLM APIは呼ばず、Pydanticスキーマ自体が「不正な形のデータ」を
正しく弾けることを確認する(malformed responseの検出)。
"""

import pytest
from pydantic import ValidationError

from app.services.llm_schemas import ComparisonReportResult


def _valid_payload() -> dict:
    return {
        "recommendation": {
            "winner": "item_a",
            "summary": "今回の用途ではFastAPIを推奨します",
            "reason": "非同期処理とAIアプリとの相性が良いため",
        },
        "comparisons": [
            {
                "criterion": "development_speed",
                "criterion_label": "開発速度",
                "item_a_summary": "FastAPIは型ヒントを活用して高速に開発できる。",
                "item_b_summary": "Djangoは機能が豊富だが規約が多い。",
                "item_a_score": 5,
                "item_b_score": 4,
                "winner": "item_a",
            }
        ],
    }


def test_valid_response_parses_successfully():
    result = ComparisonReportResult.model_validate(_valid_payload())

    assert result.recommendation.winner.value == "item_a"
    assert result.comparisons[0].item_a_score == 5
    assert result.comparisons[0].winner.value == "item_a"


def test_score_out_of_range_is_rejected():
    payload = _valid_payload()
    payload["comparisons"][0]["item_a_score"] = 10  # 1〜5の範囲外

    with pytest.raises(ValidationError):
        ComparisonReportResult.model_validate(payload)


def test_invalid_winner_value_is_rejected():
    payload = _valid_payload()
    payload["recommendation"]["winner"] = "FastAPI"  # item_a/item_b/tie以外

    with pytest.raises(ValidationError):
        ComparisonReportResult.model_validate(payload)


def test_missing_required_field_is_rejected():
    payload = _valid_payload()
    del payload["recommendation"]["reason"]

    with pytest.raises(ValidationError):
        ComparisonReportResult.model_validate(payload)
