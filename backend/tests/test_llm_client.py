"""llm_client.generate_comparison() のretryロジックのテスト。

実際のGemini APIは呼ばず、genai.Clientをmockに差し替えて、
- 5xx(ServerError)や429はretryして最終的に成功する
- 400/401等はretryせず即座に例外を送出する
- retryしても解決しない場合は、最大試行回数で諦めて例外を送出する
ことを確認する。time.sleepもmockして、テストを実時間で待たせない。
"""

import json

import pytest
import requests
from google.genai import errors as genai_errors

import app.services.llm_client as llm_client_module
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
    # genai.Client(api_key=...)のように呼ばれても受け取れるようにしておく
    # (実際の呼び出し方法はtest_generate_comparison_passes_gemini_api_key...
    # 側で別途検証する)。
    monkeypatch.setattr(
        "app.services.llm_client.genai.Client", lambda **kwargs: _FakeClient(fake_models)
    )
    monkeypatch.setattr(
        "app.services.llm_client.time.sleep",
        lambda seconds: (sleep_calls.append(seconds) if sleep_calls is not None else None),
    )
    # jitterをテストで無効化し、backoffの具体的な秒数を決定的に検証できるようにする。
    monkeypatch.setattr("app.services.llm_client.random.uniform", lambda a, b: 0)


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


def test_generate_comparison_passes_gemini_api_key_from_settings_explicitly(monkeypatch):
    """genai.Client()が、SDKバージョンによって挙動が変わりうる環境変数の
    自動探索(GOOGLE_API_KEY/GEMINI_API_KEY)に頼らず、Settings経由で読んだ
    GEMINI_API_KEYを`api_key=`として明示的に渡していることを確認する
    (dry runで発覚した、SDKが参照する環境変数名との食い違いの回帰テスト)。
    """
    captured_kwargs: dict = {}

    def _fake_client_factory(**kwargs):
        captured_kwargs.update(kwargs)
        return _FakeClient(_FakeModels([_valid_response()]))

    monkeypatch.setattr("app.services.llm_client.genai.Client", _fake_client_factory)
    # 実際のキー値は使わず、テスト専用のダミー値で「Settingsの値がそのまま
    # 渡されているか」だけを検証する。
    monkeypatch.setattr(
        "app.services.llm_client.settings.gemini_api_key", "dummy-test-api-key"
    )

    _call_generate_comparison()

    assert captured_kwargs == {"api_key": "dummy-test-api-key"}


# --- Phase 4.1: rate-limit resilience(backoff/jitter/Retry-After/pacing) ---


def test_backoff_increases_exponentially_across_attempts(monkeypatch):
    monkeypatch.setattr(llm_client_module.random, "uniform", lambda a, b: 0)
    fake_503 = make_genai_api_error(
        genai_errors.ServerError, 503, "overloaded", "UNAVAILABLE"
    )

    first = llm_client_module._compute_backoff_seconds(0, fake_503)
    second = llm_client_module._compute_backoff_seconds(1, fake_503)

    assert first == 1.0  # base(1.0) * 2**0
    assert second == 2.0  # base(1.0) * 2**1
    assert second > first


def test_backoff_includes_jitter(monkeypatch):
    monkeypatch.setattr(llm_client_module.random, "uniform", lambda a, b: 0.3)
    fake_503 = make_genai_api_error(
        genai_errors.ServerError, 503, "overloaded", "UNAVAILABLE"
    )

    seconds = llm_client_module._compute_backoff_seconds(0, fake_503)

    assert seconds == pytest.approx(1.3)  # base(1.0) + jitter(0.3)


def test_backoff_prefers_retry_after_header_when_present(monkeypatch):
    monkeypatch.setattr(llm_client_module.random, "uniform", lambda a, b: 0.3)
    response = requests.Response()
    response.status_code = 429
    response._content = json.dumps(
        {"error": {"message": "rate limited", "status": "RESOURCE_EXHAUSTED"}}
    ).encode("utf-8")
    response.headers["Retry-After"] = "7"
    fake_429 = genai_errors.ClientError(429, response)

    seconds = llm_client_module._compute_backoff_seconds(0, fake_429)

    # Retry-Afterが取得できる場合は、指数バックオフ+jitterより優先する。
    assert seconds == 7.0


def test_backoff_falls_back_to_exponential_when_no_retry_after_header(monkeypatch):
    monkeypatch.setattr(llm_client_module.random, "uniform", lambda a, b: 0)
    fake_503 = make_genai_api_error(
        genai_errors.ServerError, 503, "overloaded", "UNAVAILABLE"
    )

    seconds = llm_client_module._compute_backoff_seconds(0, fake_503)

    assert seconds == 1.0


class _FakeClock:
    """time.monotonic()の代わりに使う、手動で進められるfakeクロック。"""

    def __init__(self, start: float = 0.0):
        self._now = start

    def advance(self, seconds: float) -> None:
        self._now += seconds

    def __call__(self) -> float:
        return self._now


def test_pace_gemini_request_waits_for_configured_minimum_interval(monkeypatch):
    monkeypatch.setattr(llm_client_module, "_last_gemini_request_at", None)
    monkeypatch.setattr(
        llm_client_module.settings, "gemini_min_request_interval_seconds", 5.0
    )
    clock = _FakeClock(start=100.0)
    monkeypatch.setattr(llm_client_module.time, "monotonic", clock)
    sleep_calls: list[float] = []
    monkeypatch.setattr(
        llm_client_module.time,
        "sleep",
        lambda seconds: (sleep_calls.append(seconds), clock.advance(seconds)),
    )

    llm_client_module.pace_gemini_request()  # 初回は待機しない
    assert sleep_calls == []

    clock.advance(1.0)  # 1秒しか経っていない(5秒間隔に満たない)
    llm_client_module.pace_gemini_request()

    assert sleep_calls == [pytest.approx(4.0)]  # 5.0 - 1.0


def test_pace_gemini_request_skips_wait_when_interval_already_elapsed(monkeypatch):
    monkeypatch.setattr(llm_client_module, "_last_gemini_request_at", None)
    monkeypatch.setattr(
        llm_client_module.settings, "gemini_min_request_interval_seconds", 5.0
    )
    clock = _FakeClock(start=100.0)
    monkeypatch.setattr(llm_client_module.time, "monotonic", clock)
    sleep_calls: list[float] = []
    monkeypatch.setattr(
        llm_client_module.time,
        "sleep",
        lambda seconds: (sleep_calls.append(seconds), clock.advance(seconds)),
    )

    llm_client_module.pace_gemini_request()
    clock.advance(10.0)  # 間隔(5秒)より十分経過している
    llm_client_module.pace_gemini_request()

    assert sleep_calls == []


def test_pace_gemini_request_is_noop_when_min_interval_is_zero(monkeypatch):
    monkeypatch.setattr(llm_client_module, "_last_gemini_request_at", None)
    monkeypatch.setattr(
        llm_client_module.settings, "gemini_min_request_interval_seconds", 0
    )
    clock = _FakeClock(start=100.0)
    monkeypatch.setattr(llm_client_module.time, "monotonic", clock)
    sleep_calls: list[float] = []
    monkeypatch.setattr(llm_client_module.time, "sleep", lambda s: sleep_calls.append(s))

    llm_client_module.pace_gemini_request()
    llm_client_module.pace_gemini_request()

    assert sleep_calls == []
