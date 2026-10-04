"""llm_client.generate_comparison() のretryロジックのテスト。

実際のGemini APIは呼ばず、genai.Clientをmockに差し替えて、
- 5xx(ServerError)や429はretryして最終的に成功する
- 400/401等はretryせず即座に例外を送出する
- retryしても解決しない場合は、最大試行回数で諦めて例外を送出する
ことを確認する。time.sleepもmockして、テストを実時間で待たせない。
"""

import json
import logging

import pytest
import requests
from google.genai import errors as genai_errors

import app.services.llm_client as llm_client_module
from app.services.llm_client import _build_prompt, generate_comparison
from app.services.llm_schemas import ComparisonReportResult
from app.services.search_client import SearchResultItem
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


# --- Phase 5F: Observability (logging) --------------------------------------


def _gemini_request_log_messages(caplog) -> list[str]:
    return [r.message for r in caplog.records if r.message.startswith("gemini_request")]


def test_generate_structured_logs_single_successful_attempt(monkeypatch, caplog):
    fake_models = _FakeModels([_valid_response()])
    _patch_client(monkeypatch, fake_models)

    with caplog.at_level(logging.INFO, logger="app.services.llm_client"):
        _call_generate_comparison()

    logs = _gemini_request_log_messages(caplog)
    assert len(logs) == 1
    assert "request_type=comparison" in logs[0]
    assert "attempt=1/3" in logs[0]
    assert "outcome=success" in logs[0]


def test_generate_structured_logs_failure_then_success_with_increasing_attempt_numbers(
    monkeypatch, caplog
):
    fake_503 = make_genai_api_error(
        genai_errors.ServerError, 503, "overloaded", "UNAVAILABLE"
    )
    fake_models = _FakeModels([fake_503, _valid_response()])
    sleep_calls: list[float] = []
    _patch_client(monkeypatch, fake_models, sleep_calls)

    with caplog.at_level(logging.INFO, logger="app.services.llm_client"):
        _call_generate_comparison()

    logs = _gemini_request_log_messages(caplog)
    assert len(logs) == 2
    assert "attempt=1/3" in logs[0] and "outcome=failure" in logs[0]
    assert "attempt=2/3" in logs[1] and "outcome=success" in logs[1]
    # backoffは1回だけ計算され、ログと実際のtime.sleep()呼び出しが同じ値であること
    # (再計算してjitterが再抽選されていないことの確認)。
    assert f"backoff_s={sleep_calls[0]:.2f}" in logs[0]


def test_generate_structured_logs_retry_after_usage_when_present(monkeypatch, caplog):
    response = requests.Response()
    response.status_code = 429
    response._content = json.dumps(
        {"error": {"message": "rate limited", "status": "RESOURCE_EXHAUSTED"}}
    ).encode("utf-8")
    response.headers["Retry-After"] = "7"
    fake_429 = genai_errors.ClientError(429, response)
    fake_models = _FakeModels([fake_429, _valid_response()])
    sleep_calls: list[float] = []
    _patch_client(monkeypatch, fake_models, sleep_calls)

    with caplog.at_level(logging.INFO, logger="app.services.llm_client"):
        _call_generate_comparison()

    logs = _gemini_request_log_messages(caplog)
    assert "retry_after_used=True" in logs[0]
    assert "backoff_s=7.00" in logs[0]
    assert sleep_calls == [7.0]


def test_generate_structured_logs_all_attempts_when_every_attempt_fails(monkeypatch, caplog):
    fake_503 = make_genai_api_error(
        genai_errors.ServerError, 503, "overloaded", "UNAVAILABLE"
    )
    fake_models = _FakeModels([fake_503, fake_503, fake_503])
    sleep_calls: list[float] = []
    _patch_client(monkeypatch, fake_models, sleep_calls)

    with caplog.at_level(logging.INFO, logger="app.services.llm_client"):
        with pytest.raises(genai_errors.ServerError):
            _call_generate_comparison()

    logs = _gemini_request_log_messages(caplog)
    assert len(logs) == 3
    assert all("outcome=failure" in m for m in logs)
    assert "attempt=1/3" in logs[0]
    assert "attempt=2/3" in logs[1]
    assert "attempt=3/3" in logs[2]
    # 最後のattemptはretryしない(=backoffを計算しない)ため、該当フィールドが無い。
    assert "backoff_s" not in logs[2]


def test_generate_structured_logs_never_contain_prompt_or_source_text(monkeypatch, caplog):
    """ログにprompt全文・Source本文等の大量/機密テキストが含まれないことの
    回帰テスト(Phase 5F設計で明示的に禁止した事項)。"""
    secret_marker = "SECRET_SOURCE_BODY_SHOULD_NOT_APPEAR_IN_LOGS"
    fake_models = _FakeModels([_valid_response()])
    _patch_client(monkeypatch, fake_models)

    with caplog.at_level(logging.INFO, logger="app.services.llm_client"):
        generate_comparison(
            item_a="FastAPI",
            item_b="Django",
            goal="test",
            criteria=["development_speed"],
            sources={
                1: SearchResultItem(title="t", url="https://example.com", content=secret_marker)
            },
        )

    for record in caplog.records:
        assert secret_marker not in record.message
        assert len(record.message) < 300  # 大量テキストが紛れ込んでいないことの簡易確認


# --- Phase 4.1: rate-limit resilience(backoff/jitter/Retry-After/pacing) ---


def test_backoff_increases_exponentially_across_attempts(monkeypatch):
    monkeypatch.setattr(llm_client_module.random, "uniform", lambda a, b: 0)
    fake_503 = make_genai_api_error(
        genai_errors.ServerError, 503, "overloaded", "UNAVAILABLE"
    )

    first, first_used_retry_after = llm_client_module._compute_backoff_seconds(0, fake_503)
    second, second_used_retry_after = llm_client_module._compute_backoff_seconds(1, fake_503)

    assert first == 1.0  # base(1.0) * 2**0
    assert second == 2.0  # base(1.0) * 2**1
    assert second > first
    assert first_used_retry_after is False
    assert second_used_retry_after is False


def test_backoff_includes_jitter(monkeypatch):
    monkeypatch.setattr(llm_client_module.random, "uniform", lambda a, b: 0.3)
    fake_503 = make_genai_api_error(
        genai_errors.ServerError, 503, "overloaded", "UNAVAILABLE"
    )

    seconds, used_retry_after = llm_client_module._compute_backoff_seconds(0, fake_503)

    assert seconds == pytest.approx(1.3)  # base(1.0) + jitter(0.3)
    assert used_retry_after is False


def test_backoff_prefers_retry_after_header_when_present(monkeypatch):
    monkeypatch.setattr(llm_client_module.random, "uniform", lambda a, b: 0.3)
    response = requests.Response()
    response.status_code = 429
    response._content = json.dumps(
        {"error": {"message": "rate limited", "status": "RESOURCE_EXHAUSTED"}}
    ).encode("utf-8")
    response.headers["Retry-After"] = "7"
    fake_429 = genai_errors.ClientError(429, response)

    seconds, used_retry_after = llm_client_module._compute_backoff_seconds(0, fake_429)

    # Retry-Afterが取得できる場合は、指数バックオフ+jitterより優先する。
    assert seconds == 7.0
    assert used_retry_after is True


def test_backoff_falls_back_to_exponential_when_no_retry_after_header(monkeypatch):
    monkeypatch.setattr(llm_client_module.random, "uniform", lambda a, b: 0)
    fake_503 = make_genai_api_error(
        genai_errors.ServerError, 503, "overloaded", "UNAVAILABLE"
    )

    seconds, used_retry_after = llm_client_module._compute_backoff_seconds(0, fake_503)

    assert seconds == 1.0
    assert used_retry_after is False


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

    first_wait = llm_client_module.pace_gemini_request()  # 初回は待機しない
    assert sleep_calls == []
    assert first_wait == 0.0

    clock.advance(1.0)  # 1秒しか経っていない(5秒間隔に満たない)
    second_wait = llm_client_module.pace_gemini_request()

    assert sleep_calls == [pytest.approx(4.0)]  # 5.0 - 1.0
    assert second_wait == pytest.approx(4.0)  # 実際に待機した秒数を返す(Phase 5F)


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
    wait = llm_client_module.pace_gemini_request()

    assert sleep_calls == []
    assert wait == 0.0  # 待機不要の場合は0.0を返す(Phase 5F)


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


# --- _build_prompt: Phase 5D-e (Claim Grounding, prompt-only) --------------


def _sample_sources() -> dict[int, SearchResultItem]:
    return {
        1: SearchResultItem(
            title="Flask Docs", url="https://flask.palletsprojects.com", content="Flask is a framework."
        ),
    }


def test_build_prompt_requires_summary_to_be_supportable_by_cited_chunks():
    prompt = _build_prompt("Flask", "FastAPI", "個人開発用", ["learning_curve"], _sample_sources())

    assert "情報源(chunk)によって実際に" in prompt
    assert "支持できる内容だけを書くこと" in prompt
    assert "事前学習知識で" in prompt
    assert "補って書かない" in prompt


def test_build_prompt_instructs_qualitative_wording_when_sources_disagree_on_numbers():
    prompt = _build_prompt("Flask", "FastAPI", "個人開発用", ["ecosystem"], _sample_sources())

    assert "数値が食い違う場合" in prompt
    assert "定性的な表現" in prompt


def test_build_prompt_no_longer_permits_general_knowledge_filler():
    """旧い許可文言(一般的な知識を参考程度に述べてもよい)は、情報源に
    記載が無いケースのfallbackとしてもはや許可されていない(退行防止)。"""
    prompt = _build_prompt("Flask", "FastAPI", "個人開発用", ["learning_curve"], _sample_sources())

    assert "一般的な知識を参考程度に述べてもよい" not in prompt
    assert "一般的な知識で具体的な数値・固有の事実を補わない" in prompt


def test_build_prompt_separates_recommendation_as_ai_interpretation_layer():
    prompt = _build_prompt("Flask", "FastAPI", "個人開発用", ["learning_curve"], _sample_sources())

    assert "AIが解釈・総合判断する層" in prompt
    assert "個々のcitationを挙げる必要はない" in prompt
