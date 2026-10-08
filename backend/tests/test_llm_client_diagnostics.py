"""Phase 5G: Error diagnostics(429/503のstatus/reason/quota_metric/quota_id)
のテスト。

実際のGemini APIは呼ばない。genai_errors.ClientError/ServerErrorを
conftest.make_genai_api_error()でGoogleのエラーレスポンス形状(本物の
requests.Response)を模して組み立て、`_extract_error_diagnostics()`が
安全にstatus/reason/quota_metric/quota_idを取り出せること、かつ
Googleのレスポンス形状が想定と異なっても例外を送出しない(best-effort)
ことを確認する。
"""

import logging

import pytest
from google.genai import errors as genai_errors

import app.services.llm_client as llm_client_module
from app.services.llm_client import _extract_error_diagnostics, generate_comparison
from conftest import make_genai_api_error


def _quota_failure_details(quota_metric: str, quota_id: str) -> list[dict]:
    return [
        {
            "@type": "type.googleapis.com/google.rpc.QuotaFailure",
            "violations": [{"quotaMetric": quota_metric, "quotaId": quota_id}],
        },
        {
            "@type": "type.googleapis.com/google.rpc.ErrorInfo",
            "reason": "RATE_LIMIT_EXCEEDED",
            "domain": "generativelanguage.googleapis.com",
        },
    ]


# --- _extract_error_diagnostics(): 正常系 ------------------------------------


def test_extract_error_diagnostics_reads_status_reason_and_quota_fields():
    exc = make_genai_api_error(
        genai_errors.ClientError,
        429,
        "rate limited",
        "RESOURCE_EXHAUSTED",
        details=_quota_failure_details(
            "generativelanguage.googleapis.com/generate_requests_per_model_per_minute",
            "GenerateRequestsPerMinutePerProjectPerModel-FreeTier",
        ),
    )

    diagnostics = _extract_error_diagnostics(exc)

    assert diagnostics.status == "RESOURCE_EXHAUSTED"
    assert diagnostics.reason == "RATE_LIMIT_EXCEEDED"
    assert diagnostics.quota_metric == (
        "generativelanguage.googleapis.com/generate_requests_per_model_per_minute"
    )
    assert diagnostics.quota_id == "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"


def test_extract_error_diagnostics_for_503_has_status_but_no_quota_fields():
    exc = make_genai_api_error(genai_errors.ServerError, 503, "overloaded", "UNAVAILABLE")

    diagnostics = _extract_error_diagnostics(exc)

    assert diagnostics.status == "UNAVAILABLE"
    assert diagnostics.reason is None
    assert diagnostics.quota_metric is None
    assert diagnostics.quota_id is None


# --- _extract_error_diagnostics(): defensive parsing(未知schema) -----------


def test_extract_error_diagnostics_does_not_raise_when_details_is_missing():
    exc = make_genai_api_error(genai_errors.ClientError, 429, "rate limited", "RESOURCE_EXHAUSTED")

    diagnostics = _extract_error_diagnostics(exc)

    assert diagnostics.status == "RESOURCE_EXHAUSTED"
    assert diagnostics.reason is None
    assert diagnostics.quota_metric is None
    assert diagnostics.quota_id is None


def test_extract_error_diagnostics_does_not_raise_when_details_entries_are_malformed():
    """Google側のレスポンス形状が将来変わっても(リストの中身が辞書でない、
    violationsが空/非リスト等)、診断抽出自体が例外を送出しないことを確認する。
    """
    exc = make_genai_api_error(
        genai_errors.ClientError,
        429,
        "rate limited",
        "RESOURCE_EXHAUSTED",
        details=[
            "not-a-dict",
            {"@type": "type.googleapis.com/google.rpc.ErrorInfo"},  # reasonキー無し
            {"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": "not-a-list"},
            {"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": []},
            None,
        ],
    )

    diagnostics = _extract_error_diagnostics(exc)

    assert diagnostics.status == "RESOURCE_EXHAUSTED"
    assert diagnostics.reason is None
    assert diagnostics.quota_metric is None
    assert diagnostics.quota_id is None


def test_extract_error_diagnostics_does_not_raise_for_exception_without_api_error_attrs():
    """genai_errors.APIError以外の任意のExceptionを渡しても壊れない
    (呼び出し側の例外処理の構造が将来変わっても安全側に倒す)。"""
    diagnostics = _extract_error_diagnostics(ValueError("something else"))

    assert diagnostics.status is None
    assert diagnostics.reason is None
    assert diagnostics.quota_metric is None
    assert diagnostics.quota_id is None


def test_extract_error_diagnostics_never_exposes_message_field():
    """messageは今回ログ設計から意図的に除外している(_ErrorDiagnosticsに
    フィールド自体が存在しないことを回帰テストする)。"""
    exc = make_genai_api_error(genai_errors.ClientError, 429, "SECRET_MESSAGE_TEXT", "RESOURCE_EXHAUSTED")

    diagnostics = _extract_error_diagnostics(exc)

    assert not hasattr(diagnostics, "message")


# --- 実際のログ出力への反映 --------------------------------------------------


class _FakeModelsAlwaysFails:
    def __init__(self, exc):
        self._exc = exc
        self.call_count = 0

    def generate_content(self, **kwargs):
        self.call_count += 1
        raise self._exc


class _FakeClient:
    def __init__(self, models):
        self.models = models


def _gemini_request_log_messages(caplog) -> list[str]:
    return [r.message for r in caplog.records if r.message.startswith("gemini_request")]


def test_generate_structured_log_includes_diagnostics_fields_on_final_failure(monkeypatch, caplog):
    exc = make_genai_api_error(
        genai_errors.ClientError,
        429,
        "rate limited",
        "RESOURCE_EXHAUSTED",
        details=_quota_failure_details(
            "generativelanguage.googleapis.com/generate_requests_per_model_per_day",
            "GenerateRequestsPerDayPerProjectPerModel-FreeTier",
        ),
    )
    fake_models = _FakeModelsAlwaysFails(exc)
    monkeypatch.setattr(
        llm_client_module.genai, "Client", lambda **kwargs: _FakeClient(fake_models)
    )
    monkeypatch.setattr(llm_client_module.time, "sleep", lambda s: None)
    monkeypatch.setattr(llm_client_module.random, "uniform", lambda a, b: 0)

    with caplog.at_level(logging.INFO, logger="app.services.llm_client"):
        with pytest.raises(genai_errors.ClientError):
            generate_comparison(
                item_a="FastAPI", item_b="Django", goal="test",
                criteria=["development_speed"], sources={},
            )

    logs = _gemini_request_log_messages(caplog)
    last_log = logs[-1]
    assert "error_status=RESOURCE_EXHAUSTED" in last_log
    assert "reason=RATE_LIMIT_EXCEEDED" in last_log
    assert "quota_metric=generativelanguage.googleapis.com/generate_requests_per_model_per_day" in last_log
    assert "quota_id=GenerateRequestsPerDayPerProjectPerModel-FreeTier" in last_log


def test_generate_structured_log_never_contains_raw_message_text(monkeypatch, caplog):
    """messageフィールド(自由文)がログに混入しないことの回帰テスト。"""
    secret_message = "SECRET_MESSAGE_SHOULD_NOT_APPEAR_IN_LOGS"
    exc = make_genai_api_error(genai_errors.ServerError, 503, secret_message, "UNAVAILABLE")
    fake_models = _FakeModelsAlwaysFails(exc)
    monkeypatch.setattr(
        llm_client_module.genai, "Client", lambda **kwargs: _FakeClient(fake_models)
    )
    monkeypatch.setattr(llm_client_module.time, "sleep", lambda s: None)
    monkeypatch.setattr(llm_client_module.random, "uniform", lambda a, b: 0)

    with caplog.at_level(logging.INFO, logger="app.services.llm_client"):
        with pytest.raises(genai_errors.ServerError):
            generate_comparison(
                item_a="FastAPI", item_b="Django", goal="test",
                criteria=["development_speed"], sources={},
            )

    for record in caplog.records:
        assert secret_message not in record.message
