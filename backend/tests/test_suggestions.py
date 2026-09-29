"""POST /suggest-criteria のテスト。

Suggest Pointsは、TavilyもResearch/Source/Evidenceも一切作らず、
Geminiのみ(1 operation、内部max 2 attempts)を呼ぶ補助APIであることを
確認する。実際のGemini呼び出しは行わず、
app.api.suggestions.generate_criteria_suggestions をmonkeypatchで
差し替える(test_research.pyがgenerate_comparisonをmockする方式と同じ)。
"""

import pytest
from google.genai import errors as genai_errors

from app.db.session import SessionLocal
from app.models.research import Research
from app.services.llm_schemas import CriteriaSuggestionsResult, CriterionSuggestionItem
from conftest import make_genai_api_error

VALID_PAYLOAD = {
    "item_a": "PostgreSQL",
    "item_b": "MongoDB",
    "goal": "SNS投稿を大量保存したい",
    "existing_criteria": ["development_speed"],
}


def _canned_result(names: list[str]) -> CriteriaSuggestionsResult:
    return CriteriaSuggestionsResult(
        suggestions=[
            CriterionSuggestionItem(name=name, reason=f"{name}が重要な理由")
            for name in names
        ]
    )


def _mock_suggestions(monkeypatch, result: CriteriaSuggestionsResult):
    captured: dict = {}

    def _fake_generate(**kwargs):
        captured.update(kwargs)
        return result

    monkeypatch.setattr(
        "app.api.suggestions.generate_criteria_suggestions", _fake_generate
    )
    return captured


def _research_count() -> int:
    db = SessionLocal()
    try:
        return db.query(Research).count()
    finally:
        db.close()


def test_suggest_criteria_success_returns_suggestions(client, monkeypatch):
    _mock_suggestions(monkeypatch, _canned_result(["スキーマ柔軟性", "クエリ能力"]))

    response = client.post("/suggest-criteria", json=VALID_PAYLOAD)

    assert response.status_code == 200
    body = response.json()
    assert body["suggestions"] == [
        {"name": "スキーマ柔軟性", "reason": "スキーマ柔軟性が重要な理由"},
        {"name": "クエリ能力", "reason": "クエリ能力が重要な理由"},
    ]


@pytest.mark.parametrize("missing_field", ["item_a", "item_b", "goal"])
def test_suggest_criteria_missing_required_field_returns_422(missing_field, client):
    payload = {k: v for k, v in VALID_PAYLOAD.items() if k != missing_field}

    response = client.post("/suggest-criteria", json=payload)

    assert response.status_code == 422


def test_suggest_criteria_without_existing_criteria_is_accepted(monkeypatch, client):
    """existing_criteriaはoptional(デフォルト空リスト)。"""
    _mock_suggestions(monkeypatch, _canned_result(["クエリ能力"]))
    payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "existing_criteria"}

    response = client.post("/suggest-criteria", json=payload)

    assert response.status_code == 200


def test_suggest_criteria_passes_existing_criteria_to_service(monkeypatch, client):
    captured = _mock_suggestions(monkeypatch, _canned_result(["クエリ能力"]))

    client.post("/suggest-criteria", json=VALID_PAYLOAD)

    assert captured["existing_criteria"] == ["development_speed"]
    assert captured["item_a"] == "PostgreSQL"
    assert captured["item_b"] == "MongoDB"
    assert captured["goal"] == "SNS投稿を大量保存したい"


def test_suggest_criteria_caps_at_5_suggestions(monkeypatch, client):
    _mock_suggestions(
        monkeypatch, _canned_result([f"提案{i}" for i in range(8)])
    )

    response = client.post("/suggest-criteria", json=VALID_PAYLOAD)

    assert response.status_code == 200
    assert len(response.json()["suggestions"]) == 5


def test_suggest_criteria_dedupes_against_existing_criteria(monkeypatch, client):
    """existing_criteriaの"development_speed"と同じ意味の"開発速度"が
    提案に含まれていても除外される(backend側defense-in-depth)。"""
    _mock_suggestions(monkeypatch, _canned_result(["開発速度", "クエリ能力"]))

    response = client.post("/suggest-criteria", json=VALID_PAYLOAD)

    names = [s["name"] for s in response.json()["suggestions"]]
    assert names == ["クエリ能力"]


def test_suggest_criteria_dedupes_suggestions_against_each_other(monkeypatch, client):
    _mock_suggestions(monkeypatch, _canned_result(["コスト", "Cost", "クエリ能力"]))

    response = client.post("/suggest-criteria", json=VALID_PAYLOAD)

    names = [s["name"] for s in response.json()["suggestions"]]
    assert names == ["コスト", "クエリ能力"]


def test_suggest_criteria_authentication_error_returns_sanitized_502(monkeypatch, client):
    fake_401 = make_genai_api_error(
        genai_errors.ClientError, 401, "invalid api key", "UNAUTHENTICATED"
    )

    def _raise(**kwargs):
        raise fake_401

    monkeypatch.setattr("app.api.suggestions.generate_criteria_suggestions", _raise)

    response = client.post("/suggest-criteria", json=VALID_PAYLOAD)

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert detail == "LLM APIキーが設定されていないか無効です。"
    # 生のAPIキー・エラー本文が漏れていないことを確認する。
    assert "invalid api key" not in detail


def test_suggest_criteria_other_client_error_returns_sanitized_502_with_status(
    monkeypatch, client
):
    fake_400 = make_genai_api_error(
        genai_errors.ClientError, 400, "bad request", "INVALID_ARGUMENT"
    )

    def _raise(**kwargs):
        raise fake_400

    monkeypatch.setattr("app.api.suggestions.generate_criteria_suggestions", _raise)

    response = client.post("/suggest-criteria", json=VALID_PAYLOAD)

    assert response.status_code == 502
    assert "400" in response.json()["detail"]
    assert "bad request" not in response.json()["detail"]


def test_suggest_criteria_unexpected_error_returns_502(monkeypatch, client):
    def _raise(**kwargs):
        raise RuntimeError("network unreachable")

    monkeypatch.setattr("app.api.suggestions.generate_criteria_suggestions", _raise)

    response = client.post("/suggest-criteria", json=VALID_PAYLOAD)

    assert response.status_code == 502


def test_suggest_criteria_does_not_call_tavily(monkeypatch, client):
    """TavilyClientが構築されたら即座に失敗するようにして、Suggest Points
    がTavilyに一切触れないことを確認する。"""

    class _ExplodingTavilyClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("Suggest PointsはTavilyを呼んではいけない")

    monkeypatch.setattr("app.services.search_client.TavilyClient", _ExplodingTavilyClient)
    _mock_suggestions(monkeypatch, _canned_result(["クエリ能力"]))

    response = client.post("/suggest-criteria", json=VALID_PAYLOAD)

    assert response.status_code == 200


def test_suggest_criteria_does_not_create_research_row(monkeypatch, client):
    before = _research_count()
    _mock_suggestions(monkeypatch, _canned_result(["クエリ能力"]))

    response = client.post("/suggest-criteria", json=VALID_PAYLOAD)

    assert response.status_code == 200
    assert _research_count() == before


def test_suggest_criteria_does_not_create_research_row_even_on_error(monkeypatch, client):
    before = _research_count()

    def _raise(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("app.api.suggestions.generate_criteria_suggestions", _raise)

    client.post("/suggest-criteria", json=VALID_PAYLOAD)

    assert _research_count() == before


def test_suggest_criteria_reuses_gemini_pacing_and_retry(monkeypatch, client):
    """API層はgenerate_criteria_suggestions()を直接呼んでおり、pacing/retry
    はllm_client.py側の共通処理(_generate_structured)にそのまま委譲されて
    いる(test_llm_client_suggestions.pyでリトライ本体は別途検証済み)。
    ここではAPI経由でもその関数が呼ばれることだけを確認する。"""
    called = {"count": 0}

    def _fake_generate(**kwargs):
        called["count"] += 1
        return _canned_result(["クエリ能力"])

    monkeypatch.setattr("app.api.suggestions.generate_criteria_suggestions", _fake_generate)

    client.post("/suggest-criteria", json=VALID_PAYLOAD)

    assert called["count"] == 1
