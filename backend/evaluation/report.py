"""Evaluation結果をJSON 1本 + CSV 2本として保存する。

- run_<timestamp>.json            : 全ケースの詳細 + 集計値
- run_<timestamp>_cases.csv       : 15行(ケースごとのルールベースmetrics)
- run_<timestamp>_judge_claims.csv: LLM Judgeが判定した各claim1行分
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from evaluation.run_eval import EvaluationRunResult, build_aggregate

RESULTS_DIR = Path(__file__).parent / "results"


def _case_to_dict(case_result) -> dict:
    snap = case_result.snapshot
    m = case_result.case_metrics
    return {
        "case_id": snap.case_id,
        "research_id": snap.research_id,
        "item_a": case_result.case.item_a,
        "item_b": case_result.case.item_b,
        "criteria_requested": snap.criteria_requested,
        "status": snap.status,
        "error_message": snap.error_message,
        "latency_seconds": snap.latency_seconds,
        "sources_fetched": snap.sources_fetched,
        "sources_cited": snap.sources_cited,
        "source_utilization_rate": m.source_utilization_rate,
        "comparisons_returned": len(snap.comparisons),
        "comparison_completeness": m.comparison_completeness,
        "evidence_coverage_rate": m.evidence_coverage_rate,
        "recommendation_winner": snap.recommendation_winner,
        "recommendation_consistent": m.recommendation_consistent,
    }


def _judge_claim_rows(run_result: EvaluationRunResult) -> list[dict]:
    rows = []
    for case_id, claim in run_result.judged_claims:
        rows.append(
            {
                "case_id": case_id,
                "criterion": claim.criterion,
                "side": claim.side,
                "has_evidence": claim.has_evidence,
                "verdict": claim.verdict.value,
                "rationale": claim.rationale,
            }
        )
    return rows


def build_report_document(run_result: EvaluationRunResult, aggregate: dict | None = None) -> dict:
    aggregate = aggregate if aggregate is not None else build_aggregate(run_result)
    return {
        "run_at": run_result.run_at,
        "model": run_result.model,
        "cases": [_case_to_dict(r) for r in run_result.case_results],
        "aggregate": aggregate,
    }


def write_report(
    run_result: EvaluationRunResult,
    aggregate: dict | None = None,
    out_dir: Path | None = None,
) -> dict[str, str]:
    out_dir = out_dir or RESULTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    timestamp = run_result.run_at.replace(":", "").replace("+00:00", "Z")
    document = build_report_document(run_result, aggregate)

    json_path = out_dir / f"run_{timestamp}.json"
    json_path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    cases_csv_path = out_dir / f"run_{timestamp}_cases.csv"
    case_rows = document["cases"]
    with cases_csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(case_rows[0].keys()) if case_rows else [])
        writer.writeheader()
        writer.writerows(case_rows)

    judge_csv_path = out_dir / f"run_{timestamp}_judge_claims.csv"
    judge_rows = _judge_claim_rows(run_result)
    with judge_csv_path.open("w", newline="", encoding="utf-8") as f:
        fieldnames = ["case_id", "criterion", "side", "has_evidence", "verdict", "rationale"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(judge_rows)

    return {
        "json": str(json_path),
        "cases_csv": str(cases_csv_path),
        "judge_claims_csv": str(judge_csv_path),
    }
