"""Gemini APIの実測token使用量とTavily検索呼び出し回数を計測するための計装。

文字数からのトークン数概算はしない。google-genai>=1.2の
`GenerateContentResponse.usage_metadata`(prompt_token_count /
candidates_token_count / total_token_count)を、実際のAPI呼び出しの
戻り値からそのまま読み取る。

このモジュールは本番コード(app/services/llm_client.py,
app/services/research_runner.py)を一切変更しない。代わりに、
`app.services.llm_client.genai.Client` / `app.services.research_runner.search_technology`
を評価スクリプトの実行中だけ薄いラッパーに差し替える(with文を抜けたら元に戻す)。
発想はtests/test_llm_client.pyのmonkeypatchと同じで、内部実装(SDK内部の
リトライ処理など)には依存しない。
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator

import app.services.llm_client as llm_client_module
import app.services.research_runner as research_runner_module
from app.services.search_client import SearchResultItem


@dataclass
class GeminiCallRecord:
    prompt_token_count: int | None
    candidates_token_count: int | None
    total_token_count: int | None


def sum_usage(records: list[GeminiCallRecord]) -> dict[str, int]:
    return {
        "call_count": len(records),
        "prompt_token_count": sum(r.prompt_token_count or 0 for r in records),
        "candidates_token_count": sum(r.candidates_token_count or 0 for r in records),
        "total_token_count": sum(r.total_token_count or 0 for r in records),
    }


@dataclass
class UsageRecorder:
    """1回のEvaluation実行を通しての呼び出し実績を蓄積する。"""

    gemini_calls: list[GeminiCallRecord] = field(default_factory=list)
    search_call_count: int = 0

    def gemini_totals(self) -> dict[str, int]:
        return sum_usage(self.gemini_calls)


class _UsageCapturingModels:
    """本物の`client.models`をラップし、generate_content()の戻り値の
    usage_metadataだけをrecorderに記録して、レスポンス自体はそのまま返す。
    """

    def __init__(self, real_models, recorder: UsageRecorder):
        self._real_models = real_models
        self._recorder = recorder

    def generate_content(self, **kwargs):
        response = self._real_models.generate_content(**kwargs)
        usage = response.usage_metadata
        self._recorder.gemini_calls.append(
            GeminiCallRecord(
                prompt_token_count=getattr(usage, "prompt_token_count", None),
                candidates_token_count=getattr(usage, "candidates_token_count", None),
                total_token_count=getattr(usage, "total_token_count", None),
            )
            if usage is not None
            else GeminiCallRecord(None, None, None)
        )
        return response


class _UsageCapturingClient:
    """`genai.Client()`の戻り値の代わりに渡す薄いproxy。"""

    def __init__(self, real_client, recorder: UsageRecorder):
        self.models = _UsageCapturingModels(real_client.models, recorder)


@contextmanager
def capture_gemini_usage(recorder: UsageRecorder) -> Iterator[None]:
    """with文の中でllm_client.generate_comparison()が行うGemini呼び出しの
    usage_metadataをrecorderへ記録する。

    `app.services.llm_client.genai.Client`(クラスそのもの)を、本物のClientを
    ラップするfactory関数に差し替える。with文を抜けたら必ず元に戻す。
    """
    real_genai_client_cls = llm_client_module.genai.Client

    def _factory(*args, **kwargs):
        real_client = real_genai_client_cls(*args, **kwargs)
        return _UsageCapturingClient(real_client, recorder)

    llm_client_module.genai.Client = _factory
    try:
        yield
    finally:
        llm_client_module.genai.Client = real_genai_client_cls


@contextmanager
def count_search_calls(recorder: UsageRecorder) -> Iterator[None]:
    """with文の中でresearch_runner.run_research()が行うTavily検索呼び出し
    (search_technology)の回数をrecorderへ記録する。
    """
    real_search_technology = research_runner_module.search_technology

    def _counting_search(item_name: str) -> list[SearchResultItem]:
        recorder.search_call_count += 1
        return real_search_technology(item_name)

    research_runner_module.search_technology = _counting_search
    try:
        yield
    finally:
        research_runner_module.search_technology = real_search_technology
