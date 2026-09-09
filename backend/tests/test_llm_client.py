"""llm_client.generate_comparison() のretryロジックのテスト。

実際のGemini APIは呼ばず、genai.Clientをmockに差し替えて、
- 5xx(ServerError)や429はretryして最終的に成功する
- 400/401等はretryせず即座に例外を送出する
- retryしても解決しない場合は、最大試行回数で諦めて例外を送出する
ことを確認する。time.sleepもmockして、テストを実時間で待たせない。
"""

import pytest
from google.genai import errors as genai_errors

from app.services.llm_client import generate_comparison
from app.services.llm_schemas import ComparisonReportResult
from conftest import make_genai_api_error


def _valid_response():
    """client.models.generate_content()の正常時レスポンスを模したオブジェクト。"""

    class _FakeResponse:
        parsed = ComparisonReportResult.model_validate(
            {
                "recommendation": {
                    "winner": "item_a",
                    "summary": "summary",
                    "reason": "reason",
                },
                "comparisons": [
                    {
                        "criterion": "development_speed",
                        "criterion_label": "開発速度",
                        "item_a_summary": "a",
                        "item_b_summary": "b",
                        "item_a_score": 4,
                        "item_b_score": 3,
                        "winner": "item_a",
                    }
                ],
            }
        )

    return _FakeResponse()


class _FakeModels:
    """client.models.generate_content()を、指定した順序で返す/例外にするfake。"""

    def __init__(self, side_effects):
        self._side_effects = list(side_effects)
        self.call_count = 0

    def generate_content(self, **kwargs):
        self.call_count += 1
        effect = self._side_effects.pop(0)
        if isinstance(effect, Exception):
            raise effect
        return effect


class _FakeClient:
    def __init__(self, models):
        self.models = models


def _patch_client(monkeypatch, fake_models, sleep_calls=None):
    monkeypatch.setattr(
        "app.services.llm_client.genai.Client", lambda: _FakeClient(fake_models)
    )
    monkeypatch.setattr(
        "app.services.llm_client.time.sleep",
        lambda seconds: (sleep_calls.append(seconds) if sleep_calls is not None else None),
    )


def _call_generate_comparison():
    return generate_comparison(
        item_a="FastAPI",
        item_b="Django",
        goal="test",
        criteria=["development_speed"],
        sources={},
    )


def test_retries_on_server_error_then_succeeds(monkeypatch):
    fake_503 = make_genai_api_error(
        genai_errors.ServerError, 503, "overloaded", "UNAVAILABLE"
    )
    fake_models = _FakeModels([fake_503, _valid_response()])
    sleep_calls: list[float] = []
    _patch_client(monkeypatch, fake_models, sleep_calls)

    result = _call_generate_comparison()

    assert isinstance(result, ComparisonReportResult)
    assert fake_models.call_count == 2
    # exponential backoff: 1回目の待機は1.0秒。
    assert sleep_calls == [1.0]


def test_retries_on_rate_limit_429_then_succeeds(monkeypatch):
    fake_429 = make_genai_api_error(
        genai_errors.ClientError, 429, "rate limited", "RESOURCE_EXHAUSTED"
    )
    fake_models = _FakeModels([fake_429, _valid_response()])
    _patch_client(monkeypatch, fake_models)

    result = _call_generate_comparison()

    assert isinstance(result, ComparisonReportResult)
    assert fake_models.call_count == 2


def test_does_not_retry_on_authentication_error(monkeypatch):
    fake_401 = make_genai_api_error(
        genai_errors.ClientError, 401, "invalid api key", "UNAUTHENTICATED"
    )
    fake_models = _FakeModels([fake_401])
    _patch_client(monkeypatch, fake_models)

    with pytest.raises(genai_errors.ClientError):
        _call_generate_comparison()

    # retryせず1回で諦める。
    assert fake_models.call_count == 1


def test_does_not_retry_on_bad_request(monkeypatch):
    fake_400 = make_genai_api_error(
        genai_errors.ClientError, 400, "bad request", "INVALID_ARGUMENT"
    )
    fake_models = _FakeModels([fake_400])
    _patch_client(monkeypatch, fake_models)

    with pytest.raises(genai_errors.ClientError):
        _call_generate_comparison()

    assert fake_models.call_count == 1


def test_gives_up_after_max_attempts_on_repeated_server_error(monkeypatch):
    fake_503 = make_genai_api_error(
        genai_errors.ServerError, 503, "overloaded", "UNAVAILABLE"
    )
    # 3回連続で503(初回+retry2回すべて失敗)。
    fake_models = _FakeModels([fake_503, fake_503, fake_503])
    sleep_calls: list[float] = []
    _patch_client(monkeypatch, fake_models, sleep_calls)

    with pytest.raises(genai_errors.ServerError):
        _call_generate_comparison()

    assert fake_models.call_count == 3
    # 1回目の失敗後1.0秒、2回目の失敗後2.0秒待機し、3回目(最後)は待たずに諦める。
    assert sleep_calls == [1.0, 2.0]
