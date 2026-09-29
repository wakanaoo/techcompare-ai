"""generate_criteria_suggestions() (Suggest Points) のretryロジックのテスト。

test_llm_client.py と同じmockパターンを使うが、Suggest Pointsは
comparison生成(最大3 attempts)と異なり最大2 attemptsであることを確認する
(既存のcomparison生成側のretry回数・挙動は変更していないことを
test_llm_client.py の既存テストで別途確認する)。
"""

import pytest
from google.genai import errors as genai_errors

import app.services.llm_client as llm_client_module
from app.services.llm_client import generate_criteria_suggestions
from app.services.llm_schemas import CriteriaSuggestionsResult
from conftest import make_genai_api_error


def _valid_response():
    class _FakeResponse:
        parsed = CriteriaSuggestionsResult.model_validate(
            {
                "suggestions": [
                    {"name": "スキーマ柔軟性", "reason": "SNS投稿の形式が頻繁に変わるため"},
                ]
            }
        )

    return _FakeResponse()


class _FakeModels:
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


class _RecordingModels:
    """generate_content()に渡されたprompt(contents)を記録するfake。"""

    def __init__(self, response):
        self._response = response
        self.captured_prompts: list[str] = []

    def generate_content(self, **kwargs):
        self.captured_prompts.append(kwargs["contents"])
        return self._response


def _patch_client(monkeypatch, fake_models, sleep_calls=None):
    monkeypatch.setattr(
        "app.services.llm_client.genai.Client", lambda **kwargs: _FakeClient(fake_models)
    )
    monkeypatch.setattr(
        "app.services.llm_client.time.sleep",
        lambda seconds: (sleep_calls.append(seconds) if sleep_calls is not None else None),
    )
    monkeypatch.setattr("app.services.llm_client.random.uniform", lambda a, b: 0)


def _call_generate_criteria_suggestions(existing_criteria=None):
    return generate_criteria_suggestions(
        item_a="PostgreSQL",
        item_b="MongoDB",
        goal="SNS投稿を大量保存したい",
        existing_criteria=existing_criteria or [],
    )


def test_retries_once_on_rate_limit_429_then_succeeds(monkeypatch):
    fake_429 = make_genai_api_error(
        genai_errors.ClientError, 429, "rate limited", "RESOURCE_EXHAUSTED"
    )
    fake_models = _FakeModels([fake_429, _valid_response()])
    sleep_calls: list[float] = []
    _patch_client(monkeypatch, fake_models, sleep_calls)

    result = _call_generate_criteria_suggestions()

    assert isinstance(result, CriteriaSuggestionsResult)
    assert fake_models.call_count == 2
    assert sleep_calls == [1.0]


def test_gives_up_after_2_attempts_on_repeated_server_error(monkeypatch):
    """comparison生成の最大3 attemptsとは異なり、Suggest Pointsは
    最大2 attempts(初回+retry1回)で諦める。"""
    fake_503 = make_genai_api_error(
        genai_errors.ServerError, 503, "overloaded", "UNAVAILABLE"
    )
    fake_models = _FakeModels([fake_503, fake_503])
    sleep_calls: list[float] = []
    _patch_client(monkeypatch, fake_models, sleep_calls)

    with pytest.raises(genai_errors.ServerError):
        _call_generate_criteria_suggestions()

    assert fake_models.call_count == 2
    # 1回目の失敗後1.0秒待機し、2回目(最後)は待たずに諦める。
    assert sleep_calls == [1.0]


def test_does_not_retry_on_authentication_error(monkeypatch):
    fake_401 = make_genai_api_error(
        genai_errors.ClientError, 401, "invalid api key", "UNAUTHENTICATED"
    )
    fake_models = _FakeModels([fake_401])
    _patch_client(monkeypatch, fake_models)

    with pytest.raises(genai_errors.ClientError):
        _call_generate_criteria_suggestions()

    assert fake_models.call_count == 1


def test_existing_comparison_retry_behavior_is_unchanged(monkeypatch):
    """共通化(_generate_structured)後も、comparison生成側の最大3 attempts
    という既存挙動が変わっていないことを回帰確認する
    (test_llm_client.py側の既存テスト群でも同様に確認済みだが、Suggest
    Pointsとの比較として、ここでも明示的に確認しておく)。"""
    from app.services.llm_client import _COMPARISON_MAX_ATTEMPTS, _SUGGESTION_MAX_ATTEMPTS

    assert _COMPARISON_MAX_ATTEMPTS == 3
    assert _SUGGESTION_MAX_ATTEMPTS == 2


def test_existing_criteria_included_in_prompt(monkeypatch):
    """existing_criteriaがpromptに埋め込まれ、Geminiに重複回避の指示が
    渡っていることを確認する(要件: Base Pointsと重複しない提案を促す)。"""
    recording_models = _RecordingModels(_valid_response())
    monkeypatch.setattr(
        "app.services.llm_client.genai.Client",
        lambda **kwargs: _FakeClient(recording_models),
    )
    monkeypatch.setattr("app.services.llm_client.time.sleep", lambda seconds: None)

    _call_generate_criteria_suggestions(existing_criteria=["開発速度", "コスト"])

    assert len(recording_models.captured_prompts) == 1
    prompt = recording_models.captured_prompts[0]
    assert "開発速度" in prompt
    assert "コスト" in prompt
    assert "重複" in prompt


def test_existing_criteria_control_chars_are_sanitized_out_of_prompt(monkeypatch):
    """existing_criteriaに制御文字を含む不正な要素があっても、promptには
    そのまま混入させない(サニタイズして読み飛ばす)ことを確認する。"""
    recording_models = _RecordingModels(_valid_response())
    monkeypatch.setattr(
        "app.services.llm_client.genai.Client",
        lambda **kwargs: _FakeClient(recording_models),
    )
    monkeypatch.setattr("app.services.llm_client.time.sleep", lambda seconds: None)

    _call_generate_criteria_suggestions(existing_criteria=["開発速度\n改行混入", "  "])

    assert len(recording_models.captured_prompts) == 1
    assert "改行混入" not in recording_models.captured_prompts[0]
