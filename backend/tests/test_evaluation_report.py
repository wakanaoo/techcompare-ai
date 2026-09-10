"""evaluation.report のJSON/CSV書き出しに関するテスト。

run_evaluation()やDBは使わず、EvaluationRunResultを直接組み立てて検証する。
"""

import csv
import json

from evaluation.dataset import EvaluationCase
from evaluation.judge import ClaimJudgment, ClaimVerdict
from evaluation.metrics import CaseSnapshot, ComparisonSnapshot, compute_case_metrics
from evaluation.report import build_report_document, write_report
from evaluation.run_eval import CaseRunResult, EvaluationRunResult


def _make_case_run_result(case_id: str, status: str) -> CaseRunResult:
    case = EvaluationCase(
        case_id=case_id, item_a="Alpha", item_b="Beta", goal="goal",
        criteria=["development_speed"],
    )
    snapshot = CaseSnapshot(
        case_id=case_id,
        research_id=1,
        status=status,
        error_message=None if status == "completed" else "failed for test",
        latency_seconds=2.5,
        criteria_requested=1,
        sources_fetched=2,
        sources_cited=1,
        comparisons=(
            [ComparisonSnapshot("development_speed", "item_a", 1, 0)]
            if status == "completed"
            else []
        ),
        recommendation_winner="item_a" if status == "completed" else None,
    )
    return CaseRunResult(
        case=case,
        snapshot=snapshot,
        case_metrics=compute_case_metrics(snapshot),
        judge_input=None,
    )


def _sample_run_result() -> EvaluationRunResult:
    return EvaluationRunResult(
        run_at="2026-09-09T12:00:00+00:00",
        model="gemini-3.6-flash",
        case_results=[
            _make_case_run_result("c01", "completed"),
            _make_case_run_result("c02", "failed"),
        ],
        judge_cases_requested=["c01", "c02"],
        judged_case_ids=["c01"],
        skipped_judge_case_ids=["c02"],
        judged_claims=[
            (
                "c01",
                ClaimJudgment(
                    criterion="development_speed", side="item_a", has_evidence=True,
                    verdict=ClaimVerdict.supported, rationale="ok",
                ),
            ),
        ],
        gemini_comparison_usage={"call_count": 1, "prompt_token_count": 100, "candidates_token_count": 50, "total_token_count": 150},
        gemini_judge_usage={"call_count": 1, "prompt_token_count": 80, "candidates_token_count": 40, "total_token_count": 120},
        tavily_call_count=3,
    )


def test_build_report_document_structure():
    doc = build_report_document(_sample_run_result())

    assert doc["run_at"] == "2026-09-09T12:00:00+00:00"
    assert doc["model"] == "gemini-3.6-flash"
    assert len(doc["cases"]) == 2
    assert doc["cases"][0]["case_id"] == "c01"
    assert doc["cases"][0]["status"] == "completed"
    assert doc["aggregate"]["reliability"]["research_completion_rate"] == 0.5
    assert doc["aggregate"]["answer_quality"]["llm_judge"]["cases_succeeded"] == 1

    # JSON化できること(datetimeやEnumが生の値のまま残っていないこと)を確認する。
    json.dumps(doc, ensure_ascii=False)


def test_write_report_creates_json_and_two_csv_files(tmp_path):
    run_result = _sample_run_result()
    paths = write_report(run_result, out_dir=tmp_path)

    json_path = tmp_path / paths["json"].split("/")[-1]
    cases_csv_path = tmp_path / paths["cases_csv"].split("/")[-1]
    judge_csv_path = tmp_path / paths["judge_claims_csv"].split("/")[-1]

    assert json_path.exists()
    assert cases_csv_path.exists()
    assert judge_csv_path.exists()

    with json_path.open(encoding="utf-8") as f:
        document = json.load(f)
    assert len(document["cases"]) == 2

    with cases_csv_path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2
    assert rows[0]["case_id"] == "c01"

    with judge_csv_path.open(encoding="utf-8") as f:
        judge_rows = list(csv.DictReader(f))
    assert len(judge_rows) == 1
    assert judge_rows[0]["case_id"] == "c01"
    assert judge_rows[0]["verdict"] == "supported"
