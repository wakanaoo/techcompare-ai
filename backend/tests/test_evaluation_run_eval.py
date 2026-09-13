"""evaluation.run_eval のオーケストレーションに関するテスト。

実際のTavily/Gemini APIは呼ばない。既存tests/test_research.pyと同様に
search_technology / genai.Client をmonkeypatchし、
本番と同じ run_research() を経由してEvaluationが実行されることを確認する。
"""

import tavily.errors as tavily_errors
from google.genai import errors as genai_errors

import app.services.llm_client as llm_client_module
import app.services.research_runner as research_runner_module
from app.services.llm_schemas import ComparisonReportResult
from app.services.search_client import SearchResultItem
from conftest import make_genai_api_error
from evaluation.dataset import EvaluationCase
from evaluation.judge import CaseJudgmentResult, ClaimJudgment, ClaimVerdict
from evaluation.run_eval import build_aggregate, run_evaluation


class _FakeUsageMetadata:
    def __init__(self, prompt, candidates, total):
        self.prompt_token_count = prompt
        self.candidates_token_count = candidates
        self.total_token_count = total


class _FakeResponse:
    def __init__(self, parsed):
        self.parsed = parsed
        self.usage_metadata = _FakeUsageMetadata(100, 50, 150)


class _FakeModels:
    def __init__(self):
        self.call_count = 0

    def generate_content(self, **kwargs):
        self.call_count += 1
        schema = kwargs["config"].response_schema
        if schema is ComparisonReportResult:
            return _FakeResponse(
                ComparisonReportResult.model_validate(
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
                                "item_a_summary": "item_aの開発速度は速い。",
                                "item_b_summary": "item_bは常に最速である。",
                                "item_a_score": 4,
                                "item_b_score": 3,
                                "winner": "item_a",
                                # 引用元は無し(has_evidence=falseの経路も検証するため)。
                                "item_a_source_ids": [],
                                "item_b_source_ids": [],
                            }
                        ],
                    }
                )
            )
        if schema is CaseJudgmentResult:
            return _FakeResponse(
                CaseJudgmentResult(
                    claims=[
                        ClaimJudgment(
                            criterion="development_speed",
                            side="item_a",
                            has_evidence=False,
                            verdict=ClaimVerdict.supported,
                            rationale="断定を避けている",
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
            )
        raise AssertionError(f"unexpected response_schema: {schema}")


class _FakeClient:
    def __init__(self, models):
        self.models = models


def _fake_search(item_name: str) -> list[SearchResultItem]:
    if item_name == "Gamma":
        # 2ケース目(case_fail)は検索段階で失敗させる。
        raise tavily_errors.MissingAPIKeyError()
    return [
        SearchResultItem(
            title=f"{item_name} doc", url=f"https://example.com/{item_name}", content=f"{item_name} content"
        )
    ]


def test_run_evaluation_end_to_end(client, monkeypatch):
    """client fixtureはDB(テスト用sqlite)のテーブル作成のためだけに使う。"""
    fake_models = _FakeModels()
    monkeypatch.setattr(research_runner_module, "search_technology", _fake_search)
    monkeypatch.setattr(
        llm_client_module.genai, "Client", lambda **kwargs: _FakeClient(fake_models)
    )

    case_ok = EvaluationCase(
        case_id="t1", item_a="Alpha", item_b="Beta", goal="goal",
        criteria=["development_speed"],
    )
    case_fail = EvaluationCase(
        case_id="t2", item_a="Gamma", item_b="Delta", goal="goal",
        criteria=["development_speed"],
    )

    result = run_evaluation(cases=[case_ok, case_fail], judge_case_ids=["t1", "t2"])

    assert [r.case.case_id for r in result.case_results] == ["t1", "t2"]

    ok_result = result.case_results[0]
    fail_result = result.case_results[1]

    assert ok_result.snapshot.status == "completed"
    assert fail_result.snapshot.status == "failed"
    assert fail_result.snapshot.error_message is not None

    # t1: has_evidenceがfalseのcomparisonなので、evidence_coverage_rateは0。
    assert ok_result.case_metrics.evidence_coverage_rate == 0.0
    assert ok_result.case_metrics.comparison_completeness is True

    # Judge: t1のみ実行対象(completed)、t2はstatus!=completedなのでskip。
    assert result.judged_case_ids == ["t1"]
    assert result.skipped_judge_case_ids == ["t2"]
    assert len(result.judged_claims) == 2
    assert {c.side for _cid, c in result.judged_claims} == {"item_a", "item_b"}

    # Gemini呼び出し回数: comparison生成1回(t1のみ、t2は検索失敗でLLMまで届かない) + judge1回。
    assert result.gemini_comparison_usage["call_count"] == 1
    assert result.gemini_judge_usage["call_count"] == 1
    assert fake_models.call_count == 2

    # Tavily呼び出し回数: t1は2回(item_a, item_b)。t2はitem_a(Gamma)で即失敗するため1回のみ。
    assert result.tavily_call_count == 3

    aggregate = build_aggregate(result)
    assert aggregate["reliability"]["cases_total"] == 2
    assert aggregate["reliability"]["research_completion_rate"] == 0.5
    llm_judge = aggregate["answer_quality"]["llm_judge"]
    assert llm_judge["cases_requested"] == 2
    assert llm_judge["cases_succeeded"] == 1
    assert llm_judge["cases_failed"] == 0
    assert llm_judge["cases_not_eligible"] == ["t2"]
    assert llm_judge["claims_judged_total"] == 2
    assert llm_judge["unsupported_claim"]["total"] == 2
    assert llm_judge["unsupported_claim"]["unsupported"] == 1


def _valid_comparison_fake_response() -> _FakeResponse:
    return _FakeResponse(
        ComparisonReportResult.model_validate(
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
                        "item_a_summary": "item_aの開発速度は速い。",
                        "item_b_summary": "item_bも速い。",
                        "item_a_score": 4,
                        "item_b_score": 3,
                        "winner": "item_a",
                        "item_a_source_ids": [],
                        "item_b_source_ids": [],
                    }
                ],
            }
        )
    )


def _valid_judge_fake_response() -> _FakeResponse:
    return _FakeResponse(
        CaseJudgmentResult(
            claims=[
                ClaimJudgment(
                    criterion="development_speed",
                    side="item_a",
                    has_evidence=False,
                    verdict=ClaimVerdict.supported,
                    rationale="断定を避けている",
                ),
                ClaimJudgment(
                    criterion="development_speed",
                    side="item_b",
                    has_evidence=False,
                    verdict=ClaimVerdict.supported,
                    rationale="断定を避けている",
                ),
            ]
        )
    )


class _FakeModelsWithFlakyFirstJudgeCall:
    """比較生成は常に成功させ、Judge呼び出しだけ1回目を503相当のAPIErrorに
    し、2回目以降は成功させるfake(dry runで実際に起きた503を再現する)。
    """

    def __init__(self):
        self.call_count = 0
        self._judge_call_count = 0

    def generate_content(self, **kwargs):
        self.call_count += 1
        schema = kwargs["config"].response_schema
        if schema is ComparisonReportResult:
            return _valid_comparison_fake_response()
        if schema is CaseJudgmentResult:
            self._judge_call_count += 1
            if self._judge_call_count == 1:
                raise make_genai_api_error(
                    genai_errors.ServerError, 503, "overloaded", "UNAVAILABLE"
                )
            return _valid_judge_fake_response()
        raise AssertionError(f"unexpected response_schema: {schema}")


def _always_ok_search(item_name: str) -> list[SearchResultItem]:
    return [
        SearchResultItem(
            title=f"{item_name} doc", url=f"https://example.com/{item_name}", content=f"{item_name} content"
        )
    ]


def test_judge_failure_on_one_case_does_not_crash_the_whole_evaluation(client, monkeypatch):
    """1件目のJudge呼び出しが一時的なAPIError(503相当)になっても、
    Evaluation全体はクラッシュせず、Stage Aの結果は失われず、
    後続のJudgeケースへ処理が進み、失敗したケースが記録され、
    レポート用の結果(EvaluationRunResult)が最後まで返ることを確認する
    (dry runで発覚したバグの回帰テスト)。
    """
    fake_models = _FakeModelsWithFlakyFirstJudgeCall()
    monkeypatch.setattr(research_runner_module, "search_technology", _always_ok_search)
    monkeypatch.setattr(
        llm_client_module.genai, "Client", lambda **kwargs: _FakeClient(fake_models)
    )

    case1 = EvaluationCase(
        case_id="j1", item_a="Kappa", item_b="Lambda", goal="goal",
        criteria=["development_speed"],
    )
    case2 = EvaluationCase(
        case_id="j2", item_a="Mu", item_b="Nu", goal="goal",
        criteria=["development_speed"],
    )

    # クラッシュせず最後まで実行され、Resultが返ってくること自体がこのテストの主眼。
    result = run_evaluation(cases=[case1, case2], judge_case_ids=["j1", "j2"])

    # Stage Aは両ケースとも成功済み(Judgeの成否に関わらず失われない)。
    assert result.case_results[0].snapshot.status == "completed"
    assert result.case_results[1].snapshot.status == "completed"
    assert result.case_results[0].case_metrics.comparison_completeness is True
    assert result.case_results[1].case_metrics.comparison_completeness is True

    # 1件目は失敗として記録され、2件目は成功してJudgeが続行されている。
    assert result.judge_cases_requested == ["j1", "j2"]
    assert result.judged_case_ids == ["j2"]
    assert result.skipped_judge_case_ids == []
    assert len(result.failed_judge_cases) == 1
    failure = result.failed_judge_cases[0]
    assert failure.case_id == "j1"
    assert failure.error_type == "api_error"
    # 生のエラー本文(APIキーを含みうる情報)を含めず、定型メッセージのみ。
    assert "overloaded" not in failure.sanitized_error
    assert "503" in failure.sanitized_error

    # レポート集計: 成功ケースのclaimsだけがsemantic metricsの分母になる。
    aggregate = build_aggregate(result)
    llm_judge = aggregate["answer_quality"]["llm_judge"]
    assert llm_judge["cases_requested"] == 2
    assert llm_judge["cases_succeeded"] == 1
    assert llm_judge["cases_failed"] == 1
    assert llm_judge["cases_not_eligible"] == []
    assert llm_judge["failed_cases"] == [
        {"case_id": "j1", "error_type": "api_error", "sanitized_error": failure.sanitized_error}
    ]
    assert llm_judge["claims_judged_total"] == 2  # j2の2claimのみ

    # レポート(JSON/CSV)まで必ず生成できることを確認する。
    from pathlib import Path
    from tempfile import TemporaryDirectory

    from evaluation.report import write_report

    with TemporaryDirectory() as tmp_dir:
        paths = write_report(result, aggregate, out_dir=Path(tmp_dir))
        assert Path(paths["json"]).exists()
        assert Path(paths["cases_csv"]).exists()
        assert Path(paths["judge_claims_csv"]).exists()
