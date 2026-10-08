"""Phase 5G: Evaluationを複数日(複数プロセス実行)に分けて実行するための
resume機能のテスト。

実際のTavily/Gemini APIは呼ばない。既存tests/test_evaluation_run_eval.pyと
同様にsearch_technology / genai.Clientをmonkeypatchし、本番と同じ
run_research()を経由して動作することを確認する。stateファイルはtmp_path配下
に書き、実リポジトリのevaluation/results/resume_state/には何も残さない。
"""

from __future__ import annotations

import app.services.llm_client as llm_client_module
import app.services.research_runner as research_runner_module
import evaluation.resume_state as resume_state_module
from app.services.llm_schemas import ComparisonReportResult
from app.services.search_client import SearchResultItem
from evaluation.dataset import EvaluationCase
from evaluation.resume_state import CaseState, ResumeState, load as load_resume_state
from evaluation.run_eval import (
    build_aggregate,
    collect_stage_a_results,
    run_evaluation,
    run_stage_a_cases,
    run_stage_b_judge_and_report,
    sum_stage_a_usage_from_state,
)


class _FakeUsageMetadata:
    def __init__(self, prompt, candidates, total):
        self.prompt_token_count = prompt
        self.candidates_token_count = candidates
        self.total_token_count = total


class _FakeResponse:
    def __init__(self, parsed, prompt=100, candidates=50, total=150):
        self.parsed = parsed
        self.usage_metadata = _FakeUsageMetadata(prompt, candidates, total)


def _comparison_response(prompt=100, candidates=50, total=150) -> _FakeResponse:
    return _FakeResponse(
        ComparisonReportResult.model_validate(
            {
                "recommendation": {"winner": "item_a", "summary": "s", "reason": "r"},
                "comparisons": [
                    {
                        "criterion": "development_speed",
                        "criterion_label": "開発速度",
                        "item_a_summary": "a",
                        "item_b_summary": "b",
                        "item_a_score": 4,
                        "item_b_score": 3,
                        "winner": "item_a",
                        "item_a_citations": [],
                        "item_b_citations": [],
                    }
                ],
            }
        ),
        prompt,
        candidates,
        total,
    )


class _FakeModels:
    """全呼び出しをcomparison成功として返すfake(呼び出し回数を数える)。"""

    def __init__(self):
        self.call_count = 0

    def generate_content(self, **kwargs):
        self.call_count += 1
        from evaluation.judge import CaseJudgmentResult, ClaimJudgment, ClaimVerdict

        schema = kwargs["config"].response_schema
        if schema is ComparisonReportResult:
            return _comparison_response()
        if schema is CaseJudgmentResult:
            return _FakeResponse(
                CaseJudgmentResult(
                    claims=[
                        ClaimJudgment(
                            criterion="development_speed", side="item_a",
                            has_evidence=False, verdict=ClaimVerdict.supported, rationale="ok",
                        ),
                        ClaimJudgment(
                            criterion="development_speed", side="item_b",
                            has_evidence=False, verdict=ClaimVerdict.supported, rationale="ok",
                        ),
                    ]
                )
            )
        raise AssertionError(f"unexpected response_schema: {schema}")


class _FakeClient:
    def __init__(self, models):
        self.models = models


def _always_ok_search(query: str, **_kwargs) -> list[SearchResultItem]:
    return [
        SearchResultItem(
            title=f"doc for: {query}", url=f"https://example.com/{abs(hash(query))}",
            content=f"{query} content",
        )
    ]


def _case(case_id: str) -> EvaluationCase:
    return EvaluationCase(
        case_id=case_id, item_a="Alpha", item_b="Beta", goal="goal",
        criteria=["development_speed"],
    )


def _use_tmp_state_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(resume_state_module, "STATE_DIR", tmp_path / "resume_state")


# --- evaluation.resume_state: 単体のpersistence ------------------------------


def test_resume_state_round_trips_through_save_and_load(monkeypatch, tmp_path):
    _use_tmp_state_dir(monkeypatch, tmp_path)

    state = ResumeState.new("run-x")
    state.record_case("c01", CaseState(status="completed", research_id=1, gemini_call_count=1))
    state.record_case("c02", CaseState(status="failed", research_id=2))
    state.save()

    reloaded = load_resume_state("run-x")

    assert reloaded.run_id == "run-x"
    assert reloaded.completed_case_ids() == {"c01"}
    assert reloaded.attempted_case_ids() == {"c01", "c02"}
    assert reloaded.stage_a["c01"].research_id == 1


def test_load_resume_state_returns_fresh_state_when_file_missing(monkeypatch, tmp_path):
    _use_tmp_state_dir(monkeypatch, tmp_path)

    state = load_resume_state("never-run-before")

    assert state.run_id == "never-run-before"
    assert state.stage_a == {}


# --- run_stage_a_cases(): 成功済みcaseを再実行しない --------------------------


def test_run_stage_a_cases_skips_already_completed_cases(client, monkeypatch, tmp_path):
    """client fixtureはDBテーブル作成のためだけに使う。"""
    _use_tmp_state_dir(monkeypatch, tmp_path)
    fake_models = _FakeModels()
    monkeypatch.setattr(research_runner_module, "search_technology", _always_ok_search)
    monkeypatch.setattr(
        llm_client_module.genai, "Client", lambda **kwargs: _FakeClient(fake_models)
    )

    state = ResumeState.new("run-skip")
    case1, case2 = _case("s01"), _case("s02")

    # Day 1相当: 両ケースとも初回実行。
    run_stage_a_cases([case1, case2], state)
    assert fake_models.call_count == 2
    assert state.completed_case_ids() == {"s01", "s02"}

    # Day 2相当: 同じ2ケースに対してもう一度呼んでも、既にcompleted済みなので
    # Tavily/Geminiを一切再呼び出ししない(RPD浪費防止がこのテストの主眼)。
    run_stage_a_cases([case1, case2], state)
    assert fake_models.call_count == 2  # 増えていない


def test_run_stage_a_cases_does_not_retry_failed_cases(client, monkeypatch, tmp_path):
    """failedもcompletedと同様にterminalであり、次回実行時に再試行しない
    ことを確認する(レビュー指摘の修正: resumeを「失敗caseを成功するまで
    やり直す」仕組みにしない。1 case = 1回のStage A評価、というReliability
    比較可能性を守るための要件)。"""
    _use_tmp_state_dir(monkeypatch, tmp_path)

    import tavily.errors as tavily_errors

    def _search_fail_once_then_ok(query, **_kwargs):
        if _search_fail_once_then_ok.should_fail:
            raise tavily_errors.MissingAPIKeyError()
        return _always_ok_search(query)

    _search_fail_once_then_ok.should_fail = True

    fake_models = _FakeModels()
    monkeypatch.setattr(research_runner_module, "search_technology", _search_fail_once_then_ok)
    monkeypatch.setattr(
        llm_client_module.genai, "Client", lambda **kwargs: _FakeClient(fake_models)
    )

    state = ResumeState.new("run-no-retry")
    case1 = _case("r01")

    run_stage_a_cases([case1], state)
    assert state.stage_a["r01"].status == "failed"
    failed_research_id = state.stage_a["r01"].research_id

    # 翌日相当: 検索が復旧していても、failedは既にterminalなので再実行しない。
    # (「もう一度試行すれば成功するかもしれない」という発想自体がこの
    # Evaluationのresumeでは不適切、というのが今回の修正の趣旨)
    _search_fail_once_then_ok.should_fail = False
    run_stage_a_cases([case1], state)

    assert state.stage_a["r01"].status == "failed"  # completedに上書きされない
    assert state.stage_a["r01"].research_id == failed_research_id  # 新しいresearchも作られない


def test_run_stage_a_cases_only_executes_unattempted_cases_among_mixed_states(
    client, monkeypatch, tmp_path
):
    """completed・failed・unattemptedが混在するstateに対して実行した場合、
    unattemptedなcaseだけが実行対象になることを確認する。"""
    _use_tmp_state_dir(monkeypatch, tmp_path)
    fake_models = _FakeModels()
    monkeypatch.setattr(research_runner_module, "search_technology", _always_ok_search)
    monkeypatch.setattr(
        llm_client_module.genai, "Client", lambda **kwargs: _FakeClient(fake_models)
    )

    state = ResumeState.new("run-mixed")
    state.record_case("m01", CaseState(status="completed", research_id=999))
    state.record_case("m02", CaseState(status="failed", research_id=998))

    run_stage_a_cases([_case("m01"), _case("m02"), _case("m03")], state)

    # m01/m02は既にterminalなのでAPIは呼ばれていない(call_countが1件分=m03のみ)。
    assert fake_models.call_count == 1
    assert state.stage_a["m01"].research_id == 999  # 書き換わっていない
    assert state.stage_a["m02"].research_id == 998  # 書き換わっていない
    assert state.stage_a["m03"].status == "completed"


def test_each_case_stage_a_executed_at_most_once_across_split_runs(
    client, monkeypatch, tmp_path
):
    """複数日(複数回のrun_stage_a_cases呼び出し)に分けて実行しても、
    1 caseあたりのStage A評価(`run_research()`の呼び出し)は最大1回だけ
    であることを確認する(1 case内の既存の最大3 attempts(request単位の
    retry)はこの制約の対象外)。"""
    _use_tmp_state_dir(monkeypatch, tmp_path)
    fake_models = _FakeModels()
    monkeypatch.setattr(research_runner_module, "search_technology", _always_ok_search)
    monkeypatch.setattr(
        llm_client_module.genai, "Client", lambda **kwargs: _FakeClient(fake_models)
    )

    import evaluation.run_eval as run_eval_module

    real_run_research = run_eval_module.run_research
    call_counts: dict[int, int] = {}

    def _counting_run_research(research_id):
        call_counts[research_id] = call_counts.get(research_id, 0) + 1
        return real_run_research(research_id)

    monkeypatch.setattr(run_eval_module, "run_research", _counting_run_research)

    state = ResumeState.new("run-once")
    case_a, case_b = _case("o01"), _case("o02")

    run_stage_a_cases([case_a, case_b], state)  # Day 1相当: 両ケースとも実行。
    assert sum(call_counts.values()) == 2
    assert all(n == 1 for n in call_counts.values())

    # Day 2相当: 同じ2ケースを再度指定しても、両方すでにterminalなので
    # run_research()は一度も追加で呼ばれない。
    run_stage_a_cases([case_a, case_b], state)
    assert sum(call_counts.values()) == 2


def test_run_stage_a_cases_persists_per_case_usage(client, monkeypatch, tmp_path):
    _use_tmp_state_dir(monkeypatch, tmp_path)
    fake_models = _FakeModels()
    monkeypatch.setattr(research_runner_module, "search_technology", _always_ok_search)
    monkeypatch.setattr(
        llm_client_module.genai, "Client", lambda **kwargs: _FakeClient(fake_models)
    )

    state = ResumeState.new("run-usage")
    run_stage_a_cases([_case("u01")], state)

    case_state = state.stage_a["u01"]
    assert case_state.gemini_call_count == 1
    assert case_state.gemini_prompt_tokens == 100
    assert case_state.gemini_total_tokens == 150
    assert case_state.tavily_call_count == 3  # Phase 5D: 3クエリ/research


# --- collect_stage_a_results() / sum_stage_a_usage_from_state() -------------


def test_collect_stage_a_results_reconstructs_from_db_without_calling_apis(
    client, monkeypatch, tmp_path
):
    _use_tmp_state_dir(monkeypatch, tmp_path)
    fake_models = _FakeModels()
    monkeypatch.setattr(research_runner_module, "search_technology", _always_ok_search)
    monkeypatch.setattr(
        llm_client_module.genai, "Client", lambda **kwargs: _FakeClient(fake_models)
    )

    state = ResumeState.new("run-collect")
    case1 = _case("g01")
    run_stage_a_cases([case1], state)
    calls_after_stage_a = fake_models.call_count

    # 以後、APIが呼ばれなくなっても結果を再構築できる(DBから読むだけ)。
    monkeypatch.setattr(
        llm_client_module.genai, "Client",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("API should not be called")),
    )
    results = collect_stage_a_results([case1], state)

    assert len(results) == 1
    assert results[0].snapshot.status == "completed"
    assert fake_models.call_count == calls_after_stage_a  # 増えていない


def test_sum_stage_a_usage_from_state_aggregates_across_cases(monkeypatch, tmp_path):
    _use_tmp_state_dir(monkeypatch, tmp_path)
    state = ResumeState.new("run-sum")
    state.record_case(
        "a", CaseState(status="completed", research_id=1, gemini_call_count=1,
                        gemini_prompt_tokens=100, gemini_candidates_tokens=50,
                        gemini_total_tokens=150, tavily_call_count=3)
    )
    state.record_case(
        "b", CaseState(status="completed", research_id=2, gemini_call_count=1,
                        gemini_prompt_tokens=200, gemini_candidates_tokens=80,
                        gemini_total_tokens=280, tavily_call_count=3)
    )

    gemini_usage, tavily_call_count = sum_stage_a_usage_from_state(state)

    assert gemini_usage == {
        "call_count": 2, "prompt_token_count": 300,
        "candidates_token_count": 130, "total_token_count": 430,
    }
    assert tavily_call_count == 6


# --- run_stage_b_judge_and_report(): Stage Aと独立したJudge実行 -------------


def test_run_stage_b_judge_and_report_raises_when_some_case_not_attempted(monkeypatch, tmp_path):
    _use_tmp_state_dir(monkeypatch, tmp_path)
    state = ResumeState.new("run-missing")
    state.record_case("only-one", CaseState(status="completed", research_id=1))

    import pytest

    with pytest.raises(RuntimeError, match="missing-case"):
        run_stage_b_judge_and_report(
            state, all_cases=[_case("only-one"), _case("missing-case")],
            out_dir=tmp_path,
        )


def test_run_stage_b_judge_and_report_produces_same_shape_report_as_single_shot_eval(
    client, monkeypatch, tmp_path
):
    """複数日に分けて実行した結果(2ケースをday1/day2相当で分けて実行し、
    day3相当でJudgeのみ実行)が、既存run_evaluation()(1プロセス一括実行)と
    同じ形式(JSON+CSV、aggregate構造)の最終レポートに集約できることを確認する。
    """
    _use_tmp_state_dir(monkeypatch, tmp_path)
    fake_models = _FakeModels()
    monkeypatch.setattr(research_runner_module, "search_technology", _always_ok_search)
    monkeypatch.setattr(
        llm_client_module.genai, "Client", lambda **kwargs: _FakeClient(fake_models)
    )

    state = ResumeState.new("run-e2e")
    case1, case2 = _case("e01"), _case("e02")

    # Day 1相当: 1ケースだけ実行。
    run_stage_a_cases([case1], state)
    # Day 2相当: 別プロセスのつもりで、同じrun_idのstateを読み直して続きを実行。
    state_day2 = load_resume_state("run-e2e")
    run_stage_a_cases([case2], state_day2)

    # Day 3相当: Judgeだけ独立して実行し、最終レポートを書き出す。
    paths = run_stage_b_judge_and_report(
        state_day2, all_cases=[case1, case2], judge_case_ids=["e01", "e02"],
        out_dir=tmp_path,
    )

    import json

    document = json.loads(open(paths["json"], encoding="utf-8").read())
    assert len(document["cases"]) == 2
    assert {c["case_id"] for c in document["cases"]} == {"e01", "e02"}
    assert document["aggregate"]["reliability"]["cases_total"] == 2
    assert document["aggregate"]["reliability"]["research_completion_rate"] == 1.0
    assert document["aggregate"]["answer_quality"]["llm_judge"]["cases_succeeded"] == 2


def test_failed_case_stays_not_eligible_for_judge_and_completion_rate_reflects_it(
    client, monkeypatch, tmp_path
):
    """Stage Aでfailedだったcaseは、Judge対象に指定されていても
    not_eligible(skipped)として扱われ、Judgeのために再実行されないこと
    (レビュー指摘のポイント7)。かつ最終的なResearch Completion Rateに
    failedが0.5のような形で正しく残り、resumeによって人工的に1.0へ
    改善されないこと(ポイント6)を確認する。"""
    _use_tmp_state_dir(monkeypatch, tmp_path)

    import tavily.errors as tavily_errors

    def _search_fail_for_f02(query: str, **_kwargs):
        if "FailItem" in query:
            raise tavily_errors.MissingAPIKeyError()
        return _always_ok_search(query)

    fake_models = _FakeModels()
    monkeypatch.setattr(research_runner_module, "search_technology", _search_fail_for_f02)
    monkeypatch.setattr(
        llm_client_module.genai, "Client", lambda **kwargs: _FakeClient(fake_models)
    )

    case_ok = _case("f01")
    case_fail = EvaluationCase(
        case_id="f02", item_a="FailItem", item_b="Beta", goal="goal",
        criteria=["development_speed"],
    )

    state = ResumeState.new("run-notelig")
    run_stage_a_cases([case_ok, case_fail], state)
    assert state.stage_a["f01"].status == "completed"
    assert state.stage_a["f02"].status == "failed"

    # Judgeステージでf02を検索APIで再実行しようとしたら即座に失敗させる
    # (not eligibleとして扱われるなら、そもそも呼ばれないはず)。
    def _search_should_not_be_called(*_args, **_kwargs):
        raise AssertionError("failed case must not be re-run for Judge")

    monkeypatch.setattr(research_runner_module, "search_technology", _search_should_not_be_called)

    paths = run_stage_b_judge_and_report(
        state, all_cases=[case_ok, case_fail], judge_case_ids=["f01", "f02"],
        out_dir=tmp_path,
    )

    import json

    document = json.loads(open(paths["json"], encoding="utf-8").read())
    llm_judge = document["aggregate"]["answer_quality"]["llm_judge"]
    assert llm_judge["cases_not_eligible"] == ["f02"]
    assert llm_judge["cases_succeeded"] == 1  # f01のみ

    # f02はfailedのまま最終レポートの正式な結果として残り、Completion Rateに反映される。
    assert document["aggregate"]["reliability"]["cases_total"] == 2
    assert document["aggregate"]["reliability"]["cases_completed"] == 1
    assert document["aggregate"]["reliability"]["cases_failed"] == 1
    assert document["aggregate"]["reliability"]["research_completion_rate"] == 0.5
    statuses = {c["case_id"]: c["status"] for c in document["cases"]}
    assert statuses == {"f01": "completed", "f02": "failed"}


def test_run_stage_b_judge_and_report_does_not_call_search_technology(
    client, monkeypatch, tmp_path
):
    """Judgeステージは、Stage Aで既に完了したDB結果だけを使い、Tavily検索を
    一切呼ばないことを確認する(独立実行できる、という設計意図の確認)。"""
    _use_tmp_state_dir(monkeypatch, tmp_path)
    fake_models = _FakeModels()
    monkeypatch.setattr(research_runner_module, "search_technology", _always_ok_search)
    monkeypatch.setattr(
        llm_client_module.genai, "Client", lambda **kwargs: _FakeClient(fake_models)
    )

    state = ResumeState.new("run-no-search")
    case1 = _case("n01")
    run_stage_a_cases([case1], state)

    def _search_should_not_be_called(*_args, **_kwargs):
        raise AssertionError("Judge stage must not call Tavily search")

    monkeypatch.setattr(research_runner_module, "search_technology", _search_should_not_be_called)

    run_stage_b_judge_and_report(
        state, all_cases=[case1], judge_case_ids=["n01"], out_dir=tmp_path
    )


# --- 既存run_evaluation()への回帰影響が無いことの確認 -------------------------


def test_run_evaluation_single_shot_still_works_after_refactor(client, monkeypatch):
    """_run_judge_stage()への切り出しが、既存run_evaluation()の挙動を
    変えていないことの確認(詳細な既存テストはtest_evaluation_run_eval.py側)。"""
    fake_models = _FakeModels()
    monkeypatch.setattr(research_runner_module, "search_technology", _always_ok_search)
    monkeypatch.setattr(
        llm_client_module.genai, "Client", lambda **kwargs: _FakeClient(fake_models)
    )

    case1 = _case("z01")
    result = run_evaluation(cases=[case1], judge_case_ids=["z01"])

    assert result.case_results[0].snapshot.status == "completed"
    assert result.judged_case_ids == ["z01"]
    aggregate = build_aggregate(result)
    assert aggregate["reliability"]["research_completion_rate"] == 1.0
