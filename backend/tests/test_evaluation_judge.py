"""evaluation.judge のprompt構築・呼び出し・集計に関するテスト。

実際のGemini APIは呼ばず、genai.Clientをmockに差し替える。
"""

import logging

import pytest
from google.genai import errors as genai_errors

from evaluation.judge import (
    CaseJudgmentResult,
    ClaimJudgment,
    ClaimVerdict,
    JudgeCaseInput,
    JudgeClaimInput,
    _build_prompt,
    aggregate_judge_claims,
    run_judge_for_case,
)


def _sample_case_input() -> JudgeCaseInput:
    return JudgeCaseInput(
        case_id="c01",
        item_a="FastAPI",
        item_b="Django",
        goal="AIアプリのバックエンドとして採用したい",
        claims=[
            JudgeClaimInput(
                criterion="development_speed",
                criterion_label="開発速度",
                side="item_a",
                summary="FastAPIは型ヒントを活かして高速に開発できる。",
                has_evidence=True,
                evidence_texts=["FastAPI公式ドキュメントより: 型ヒントベースの自動補完..."],
            ),
            JudgeClaimInput(
                criterion="development_speed",
                criterion_label="開発速度",
                side="item_b",
                summary="Djangoは常に最速のフレームワークである。",
                has_evidence=False,
                evidence_texts=[],
            ),
        ],
    )


def test_build_prompt_includes_evidence_text_when_has_evidence_true():
    prompt = _build_prompt(_sample_case_input())
    assert "has_evidence: true" in prompt
    assert "FastAPI公式ドキュメントより" in prompt
    assert "Evidence Correctness" in prompt


def test_build_prompt_marks_no_evidence_claims_for_unsupported_claim_check():
    prompt = _build_prompt(_sample_case_input())
    assert "has_evidence: false" in prompt
    assert "Unsupported Claim" in prompt
    assert "Djangoは常に最速のフレームワークである。" in prompt


class _FakeModels:
    def __init__(self, response):
        self._response = response
        self.call_count = 0

    def generate_content(self, **kwargs):
        self.call_count += 1
        return self._response


class _FakeClient:
    def __init__(self, models):
        self.models = models


class _FakeResponse:
    def __init__(self, parsed):
        self.parsed = parsed


def test_run_judge_for_case_returns_parsed_result(monkeypatch):
    expected = CaseJudgmentResult(
        claims=[
            ClaimJudgment(
                criterion="development_speed",
                side="item_a",
                has_evidence=True,
                verdict=ClaimVerdict.supported,
                rationale="evidenceの内容と一致する",
            ),
            ClaimJudgment(
                criterion="development_speed",
                side="item_b",
                has_evidence=False,
                verdict=ClaimVerdict.unsupported,
                rationale="根拠なく最速だと断定している",
            ),
        ]
    )
    fake_models = _FakeModels(_FakeResponse(expected))

    import evaluation.judge as judge_module

    monkeypatch.setattr(judge_module.genai, "Client", lambda **kwargs: _FakeClient(fake_models))

    result = run_judge_for_case(_sample_case_input())

    assert result == expected
    assert fake_models.call_count == 1


def test_run_judge_for_case_applies_shared_gemini_pacing(monkeypatch):
    """Judge呼び出しも、comparison生成と同じ`pace_gemini_request()`を通す
    (Gemini APIへの同じペース管理を共有する)ことを確認する。
    """
    fake_models = _FakeModels(_FakeResponse(CaseJudgmentResult(claims=[])))

    import evaluation.judge as judge_module

    monkeypatch.setattr(judge_module.genai, "Client", lambda **kwargs: _FakeClient(fake_models))

    pacing_calls = {"count": 0}

    def _fake_pace_gemini_request() -> float:
        pacing_calls["count"] += 1
        return 0.0  # pace_gemini_request()はPhase 5Fから待機秒数(float)を返す

    monkeypatch.setattr(judge_module, "pace_gemini_request", _fake_pace_gemini_request)

    run_judge_for_case(_sample_case_input())

    assert pacing_calls["count"] == 1


def test_run_judge_for_case_raises_on_malformed_response(monkeypatch):
    fake_models = _FakeModels(_FakeResponse(None))

    import evaluation.judge as judge_module

    monkeypatch.setattr(judge_module.genai, "Client", lambda **kwargs: _FakeClient(fake_models))

    with pytest.raises(ValueError):
        run_judge_for_case(_sample_case_input())


def test_run_judge_for_case_passes_gemini_api_key_from_settings_explicitly(monkeypatch):
    """app.services.llm_client.generate_comparison()と同様、judge.pyの
    genai.Client()も、SDKの環境変数自動探索(GOOGLE_API_KEY/GEMINI_API_KEYの
    どちらを見るかはSDKバージョン依存)に頼らず、Settings経由のキーを
    `api_key=`として明示的に渡していることを確認する。
    """
    captured_kwargs: dict = {}

    def _fake_client_factory(**kwargs):
        captured_kwargs.update(kwargs)
        return _FakeClient(_FakeModels(_FakeResponse(CaseJudgmentResult(claims=[]))))

    import evaluation.judge as judge_module

    monkeypatch.setattr(judge_module.genai, "Client", _fake_client_factory)
    # 実際のキー値は使わず、テスト専用のダミー値で「Settingsの値がそのまま
    # 渡されているか」だけを検証する。
    monkeypatch.setattr(judge_module.settings, "gemini_api_key", "dummy-test-api-key")

    run_judge_for_case(_sample_case_input())

    assert captured_kwargs == {"api_key": "dummy-test-api-key"}


def test_aggregate_judge_claims_splits_by_has_evidence():
    claims = [
        ClaimJudgment(
            criterion="c1", side="item_a", has_evidence=True,
            verdict=ClaimVerdict.supported, rationale="ok",
        ),
        ClaimJudgment(
            criterion="c1", side="item_b", has_evidence=True,
            verdict=ClaimVerdict.partially_supported, rationale="partial",
        ),
        ClaimJudgment(
            criterion="c2", side="item_a", has_evidence=False,
            verdict=ClaimVerdict.unsupported, rationale="overclaim",
        ),
        ClaimJudgment(
            criterion="c2", side="item_b", has_evidence=False,
            verdict=ClaimVerdict.supported, rationale="hedged, ok",
        ),
    ]

    aggregate = aggregate_judge_claims(claims)

    assert aggregate["claims_judged_total"] == 4
    assert aggregate["evidence_correctness"]["total"] == 2
    assert aggregate["evidence_correctness"]["supported"] == 1
    assert aggregate["evidence_correctness"]["partially_supported"] == 1
    assert aggregate["evidence_correctness"]["supported_rate"] == 0.5
    assert aggregate["unsupported_claim"]["total"] == 2
    assert aggregate["unsupported_claim"]["unsupported"] == 1
    assert aggregate["unsupported_claim"]["unsupported_rate"] == 0.5


def test_aggregate_judge_claims_handles_empty_list():
    aggregate = aggregate_judge_claims([])
    assert aggregate["claims_judged_total"] == 0
    assert aggregate["evidence_correctness"]["supported_rate"] is None
    assert aggregate["unsupported_claim"]["unsupported_rate"] is None


# --- Phase 5F: Observability (logging) --------------------------------------


def test_run_judge_for_case_logs_success(monkeypatch, caplog):
    expected = CaseJudgmentResult(claims=[])
    fake_models = _FakeModels(_FakeResponse(expected))

    import evaluation.judge as judge_module

    monkeypatch.setattr(judge_module.genai, "Client", lambda **kwargs: _FakeClient(fake_models))

    with caplog.at_level(logging.INFO, logger="evaluation.judge"):
        run_judge_for_case(_sample_case_input())

    logs = [r.message for r in caplog.records if r.message.startswith("gemini_request")]
    assert len(logs) == 1
    assert "request_type=judge" in logs[0]
    assert "case_id=c01" in logs[0]
    assert "attempt=1/1" in logs[0]
    assert "outcome=success" in logs[0]


def test_run_judge_for_case_logs_failure_and_still_raises(monkeypatch, caplog):
    import evaluation.judge as judge_module
    from conftest import make_genai_api_error

    fake_503 = make_genai_api_error(
        genai_errors.ServerError, 503, "overloaded", "UNAVAILABLE"
    )

    class _RaisingModels:
        def generate_content(self, **kwargs):
            raise fake_503

    monkeypatch.setattr(
        judge_module.genai, "Client", lambda **kwargs: _FakeClient(_RaisingModels())
    )

    with caplog.at_level(logging.INFO, logger="evaluation.judge"):
        with pytest.raises(genai_errors.ServerError):
            run_judge_for_case(_sample_case_input())

    logs = [r.message for r in caplog.records if r.message.startswith("gemini_request")]
    assert len(logs) == 1
    assert "request_type=judge" in logs[0]
    assert "outcome=failure" in logs[0]
    assert "status=503" in logs[0]


def test_run_judge_for_case_logs_never_contain_prompt_or_evidence_text(monkeypatch, caplog):
    """ログにprompt全文・Evidence本文等の大量/機密テキストが含まれないことの
    回帰テスト(Phase 5F設計で明示的に禁止した事項)。"""
    secret_marker = "SECRET_EVIDENCE_TEXT_SHOULD_NOT_APPEAR_IN_LOGS"
    case = JudgeCaseInput(
        case_id="c01",
        item_a="FastAPI",
        item_b="Django",
        goal="AIアプリのバックエンドとして採用したい",
        claims=[
            JudgeClaimInput(
                criterion="development_speed",
                criterion_label="開発速度",
                side="item_a",
                summary="FastAPIは型ヒントを活かして高速に開発できる。",
                has_evidence=True,
                evidence_texts=[secret_marker],
            ),
        ],
    )
    fake_models = _FakeModels(_FakeResponse(CaseJudgmentResult(claims=[])))

    import evaluation.judge as judge_module

    monkeypatch.setattr(judge_module.genai, "Client", lambda **kwargs: _FakeClient(fake_models))

    with caplog.at_level(logging.INFO, logger="evaluation.judge"):
        run_judge_for_case(case)

    for record in caplog.records:
        assert secret_marker not in record.message
        assert len(record.message) < 300
