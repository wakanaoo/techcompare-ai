"""evaluation.usage_capture のGemini usage計測 / Tavily呼び出し計数のテスト。

本物のAPIは一切呼ばない。generate_content()の戻り値のusage_metadataを
そのまま記録できること、with文を抜けたら元の関数/クラスに戻ることを確認する。
"""

import app.services.llm_client as llm_client_module
import app.services.research_runner as research_runner_module
from evaluation.usage_capture import (
    GeminiCallRecord,
    UsageRecorder,
    capture_gemini_usage,
    count_search_calls,
)


class _FakeUsageMetadata:
    def __init__(self, prompt, candidates, total):
        self.prompt_token_count = prompt
        self.candidates_token_count = candidates
        self.total_token_count = total


class _FakeResponse:
    def __init__(self, usage_metadata):
        self.usage_metadata = usage_metadata


class _FakeModels:
    def __init__(self, responses):
        self._responses = list(responses)
        self.call_count = 0

    def generate_content(self, **kwargs):
        self.call_count += 1
        return self._responses.pop(0)


class _FakeClient:
    def __init__(self, models):
        self.models = models


def test_capture_gemini_usage_records_prompt_and_candidate_tokens(monkeypatch):
    fake_models = _FakeModels(
        [
            _FakeResponse(_FakeUsageMetadata(100, 20, 120)),
            _FakeResponse(_FakeUsageMetadata(50, 10, 60)),
        ]
    )
    fake_client_factory = lambda: _FakeClient(fake_models)  # noqa: E731
    monkeypatch.setattr(llm_client_module.genai, "Client", fake_client_factory)

    recorder = UsageRecorder()
    with capture_gemini_usage(recorder):
        client = llm_client_module.genai.Client()
        client.models.generate_content(model="m", contents="1回目")
        client.models.generate_content(model="m", contents="2回目")

    assert recorder.gemini_calls == [
        GeminiCallRecord(100, 20, 120),
        GeminiCallRecord(50, 10, 60),
    ]
    assert recorder.gemini_totals() == {
        "call_count": 2,
        "prompt_token_count": 150,
        "candidates_token_count": 30,
        "total_token_count": 180,
    }
    # with文を抜けたら、直前の(テストがmonkeypatchした)factoryに戻る。
    assert llm_client_module.genai.Client is fake_client_factory


def test_capture_gemini_usage_handles_missing_usage_metadata(monkeypatch):
    fake_models = _FakeModels([_FakeResponse(None)])
    monkeypatch.setattr(
        llm_client_module.genai, "Client", lambda: _FakeClient(fake_models)
    )

    recorder = UsageRecorder()
    with capture_gemini_usage(recorder):
        llm_client_module.genai.Client().models.generate_content(model="m", contents="x")

    assert recorder.gemini_calls == [GeminiCallRecord(None, None, None)]


def test_count_search_calls_counts_and_restores(monkeypatch):
    def _fake_search(item_name):
        return [f"result-for-{item_name}"]

    monkeypatch.setattr(research_runner_module, "search_technology", _fake_search)

    recorder = UsageRecorder()
    with count_search_calls(recorder):
        research_runner_module.search_technology("FastAPI")
        research_runner_module.search_technology("Django")

    assert recorder.search_call_count == 2
    assert research_runner_module.search_technology is _fake_search
