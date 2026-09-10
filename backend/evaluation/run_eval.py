"""Phase 4 Evaluation本体: 固定Evaluation Set(既定15件)を、本番と同じ
`app.services.research_runner.run_research()` に通し、
  - 全ケースについてルールベースmetricsを算出
  - 代表ケース(既定5件)についてLLM Judgeでsemantic metricsを算出
した結果をまとめて返す。

`run_research()` / `generate_comparison()` 等の本番コードは一切変更しない。
Gemini/Tavilyの実際の呼び出し回数・token使用量は
`evaluation.usage_capture` の薄いラッパーで計測する。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from google.genai import errors as genai_errors

from app.db.session import SessionLocal
from app.models.evidence import Evidence
from app.models.research import Research
from app.services.llm_client import MODEL
from app.services.research_runner import run_research

from evaluation import metrics
from evaluation.dataset import EVALUATION_CASES, EvaluationCase, JUDGE_SAMPLE_CASE_IDS
from evaluation.judge import (
    ClaimJudgment,
    JudgeCaseInput,
    JudgeClaimInput,
    aggregate_judge_claims,
    run_judge_for_case,
)
from evaluation.usage_capture import (
    UsageRecorder,
    capture_gemini_usage,
    count_search_calls,
    sum_usage,
)


@dataclass
class CaseRunResult:
    case: EvaluationCase
    snapshot: metrics.CaseSnapshot
    case_metrics: metrics.CaseMetrics
    judge_input: JudgeCaseInput | None  # status=="completed"のケースのみ埋まる


@dataclass(frozen=True)
class JudgeFailure:
    """Judge対象として選ばれ実際に呼び出したが、失敗したケースの記録。

    「対象外だからskip」(skipped_judge_case_ids)とは区別する。
    sanitized_errorには、APIキー等の生の機密情報を含めない
    (research_runner.pyの既存のサニタイズ方針に合わせる)。
    """

    case_id: str
    error_type: str  # "api_error" | "unexpected_error"
    sanitized_error: str


def _sanitize_judge_error(exc: Exception) -> str:
    if isinstance(exc, genai_errors.APIError):
        return f"Judge呼び出しでAPIエラーが発生しました(status: {exc.code})。"
    return f"Judge呼び出し中に予期しないエラーが発生しました: {type(exc).__name__}"


@dataclass
class EvaluationRunResult:
    run_at: str
    model: str
    case_results: list[CaseRunResult]
    judge_cases_requested: list[str]  # target_judge_idsとして指定された全ケース
    judged_case_ids: list[str]  # Judgeが成功したケース
    skipped_judge_case_ids: list[str]  # Stage Aが未完了等で、そもそもJudge対象外だったケース
    failed_judge_cases: list[JudgeFailure] = field(default_factory=list)  # Judgeを試みたが失敗したケース
    judged_claims: list[tuple[str, ClaimJudgment]] = field(default_factory=list)
    gemini_comparison_usage: dict = field(default_factory=dict)
    gemini_judge_usage: dict = field(default_factory=dict)
    tavily_call_count: int = 0


def _create_pending_research(case: EvaluationCase) -> int:
    db = SessionLocal()
    try:
        research = Research(
            item_a=case.item_a,
            item_b=case.item_b,
            goal=case.goal,
            criteria=list(case.criteria),
            status="pending",
        )
        db.add(research)
        db.commit()
        db.refresh(research)
        return research.id
    finally:
        db.close()


def _evidence_side(evidence: Evidence, research: Research) -> str:
    """Evidence.claimは`f"{side_label}の{criterion_label}について"`という
    固定フォーマット(research_runner.py参照)なので、先頭が
    item_a/item_bどちらの名前かでsideを判定する。
    """
    if evidence.claim.startswith(f"{research.item_a}の"):
        return "item_a"
    if evidence.claim.startswith(f"{research.item_b}の"):
        return "item_b"
    raise ValueError(f"Evidence.claim '{evidence.claim}' からsideを判定できませんでした。")


def _load_case_result(case: EvaluationCase, research_id: int) -> CaseRunResult:
    db = SessionLocal()
    try:
        research = db.get(Research, research_id)
        if research is None:
            raise RuntimeError(f"Research {research_id} が見つかりません。")

        sources_fetched = len(research.sources)
        cited_source_ids: set[int] = set()
        comparisons_snap: list[metrics.ComparisonSnapshot] = []
        judge_claims: list[JudgeClaimInput] = []

        for comp in research.comparisons:
            a_evidences = [e for e in comp.evidences if _evidence_side(e, research) == "item_a"]
            b_evidences = [e for e in comp.evidences if _evidence_side(e, research) == "item_b"]
            for e in comp.evidences:
                cited_source_ids.add(e.source_id)

            comparisons_snap.append(
                metrics.ComparisonSnapshot(
                    criterion=comp.criterion,
                    winner=comp.winner,
                    item_a_evidence_count=len(a_evidences),
                    item_b_evidence_count=len(b_evidences),
                )
            )
            judge_claims.append(
                JudgeClaimInput(
                    criterion=comp.criterion,
                    criterion_label=comp.criterion_label,
                    side="item_a",
                    summary=comp.item_a_summary,
                    has_evidence=len(a_evidences) > 0,
                    evidence_texts=[e.evidence_text for e in a_evidences],
                )
            )
            judge_claims.append(
                JudgeClaimInput(
                    criterion=comp.criterion,
                    criterion_label=comp.criterion_label,
                    side="item_b",
                    summary=comp.item_b_summary,
                    has_evidence=len(b_evidences) > 0,
                    evidence_texts=[e.evidence_text for e in b_evidences],
                )
            )

        latency_seconds = (research.updated_at - research.created_at).total_seconds()

        snapshot = metrics.CaseSnapshot(
            case_id=case.case_id,
            research_id=research.id,
            status=research.status,
            error_message=research.error_message,
            latency_seconds=latency_seconds,
            criteria_requested=len(case.criteria),
            sources_fetched=sources_fetched,
            sources_cited=len(cited_source_ids),
            comparisons=comparisons_snap,
            recommendation_winner=research.recommendation_winner,
        )

        judge_input = None
        if research.status == "completed":
            judge_input = JudgeCaseInput(
                case_id=case.case_id,
                item_a=research.item_a,
                item_b=research.item_b,
                goal=research.goal,
                claims=judge_claims,
            )

        return CaseRunResult(
            case=case,
            snapshot=snapshot,
            case_metrics=metrics.compute_case_metrics(snapshot),
            judge_input=judge_input,
        )
    finally:
        db.close()


def run_evaluation(
    cases: list[EvaluationCase] | None = None,
    judge_case_ids: list[str] | None = None,
) -> EvaluationRunResult:
    """Evaluation Set全件を実行し、結果をまとめて返す。

    cases / judge_case_idsを指定しない場合は、`dataset.py`の既定値
    (15件・代表5件)を使う。実APIの呼び出し回数を絞ったdry runをしたい
    場合は、casesにEVALUATION_CASESの一部だけを渡せばよい。
    """
    target_cases = cases if cases is not None else EVALUATION_CASES
    target_judge_ids = judge_case_ids if judge_case_ids is not None else JUDGE_SAMPLE_CASE_IDS

    recorder = UsageRecorder()
    case_results: list[CaseRunResult] = []

    with capture_gemini_usage(recorder), count_search_calls(recorder):
        # --- Stage A: 全ケースについて本番と同じrun_research()を実行し、
        #     ルールベースmetricsの元になるスナップショットを作る ---
        for case in target_cases:
            research_id = _create_pending_research(case)
            run_research(research_id)
            case_results.append(_load_case_result(case, research_id))

        comparison_phase_call_count = len(recorder.gemini_calls)

        # --- Stage B: 代表ケースについてLLM Judgeを実行する ---
        # 1ケースのJudge失敗(一時的なAPIエラー等)でEvaluation全体を止めない。
        # Stage Aで既に成功しているルールベースmetricsは、Judgeの成否に関わらず
        # 必ず保持し、最後まで処理を進めてレポートを生成できるようにする。
        results_by_case_id = {r.case.case_id: r for r in case_results}
        judged_case_ids: list[str] = []
        skipped_judge_case_ids: list[str] = []
        failed_judge_cases: list[JudgeFailure] = []
        judged_claims: list[tuple[str, ClaimJudgment]] = []

        for case_id in target_judge_ids:
            result = results_by_case_id.get(case_id)
            if result is None or result.judge_input is None:
                # 対象ケースがEvaluation Setに無い、またはstatus!=completedで
                # Judgeできる比較結果が無い(失敗ケースはルールベースの
                # Research Completion Rateに反映済みなので、無理にJudgeしない)。
                # これは「Judgeを試みて失敗した」のではなく「そもそも対象外」。
                skipped_judge_case_ids.append(case_id)
                continue

            # run_judge_for_case()自体にはretryを追加しない(既存方針のまま)。
            # ここで例外を捕捉するのは、1ケースの一時的なAPIエラーで
            # Evaluation全体をクラッシュさせないため。
            try:
                judgment = run_judge_for_case(result.judge_input)
            except genai_errors.APIError as exc:
                failed_judge_cases.append(
                    JudgeFailure(
                        case_id=case_id,
                        error_type="api_error",
                        sanitized_error=_sanitize_judge_error(exc),
                    )
                )
                continue
            except Exception as exc:  # noqa: BLE001 - Judge1件の予期しない失敗で全体を止めない
                failed_judge_cases.append(
                    JudgeFailure(
                        case_id=case_id,
                        error_type="unexpected_error",
                        sanitized_error=_sanitize_judge_error(exc),
                    )
                )
                continue

            judged_case_ids.append(case_id)
            judged_claims.extend((case_id, claim) for claim in judgment.claims)

    gemini_comparison_usage = sum_usage(recorder.gemini_calls[:comparison_phase_call_count])
    gemini_judge_usage = sum_usage(recorder.gemini_calls[comparison_phase_call_count:])

    return EvaluationRunResult(
        run_at=datetime.now(timezone.utc).isoformat(),
        model=MODEL,
        case_results=case_results,
        judge_cases_requested=list(target_judge_ids),
        judged_case_ids=judged_case_ids,
        skipped_judge_case_ids=skipped_judge_case_ids,
        failed_judge_cases=failed_judge_cases,
        judged_claims=judged_claims,
        gemini_comparison_usage=gemini_comparison_usage,
        gemini_judge_usage=gemini_judge_usage,
        tavily_call_count=recorder.search_call_count,
    )


def build_aggregate(run_result: EvaluationRunResult) -> dict:
    """metrics.aggregate_metrics()の{reliability, answer_quality, supplementary}
    構造をベースに、Evaluation実行固有の情報(API呼び出し回数・LLM Judge結果)を
    それぞれ適切な区分に追加する。

    - Gemini/Tavilyの呼び出し回数・token使用量 → reliability
      (パイプラインがどれだけAPIを呼び、どれだけ完走したかという運用面の指標)。
    - LLM Judgeの成否・Evidence Correctness/Unsupported Claim → answer_quality
      (Judgeが成功したclaimsだけを分母にする、結果の中身の質の指標)。
    """
    case_metrics = [r.case_metrics for r in run_result.case_results]
    aggregate = metrics.aggregate_metrics(case_metrics)

    aggregate["reliability"]["gemini_usage"] = {
        "comparison_generation": run_result.gemini_comparison_usage,
        "llm_judge": run_result.gemini_judge_usage,
    }
    aggregate["reliability"]["tavily_call_count"] = run_result.tavily_call_count

    # semantic metrics(Evidence Correctness / Unsupported Claim)の分母は
    # Judgeが成功したケースのclaimsだけにする(失敗ケースは含めない)。
    judge_claims_only = [claim for _case_id, claim in run_result.judged_claims]
    aggregate["answer_quality"]["llm_judge"] = {
        "cases_requested": len(run_result.judge_cases_requested),
        "cases_succeeded": len(run_result.judged_case_ids),
        "cases_failed": len(run_result.failed_judge_cases),
        "cases_not_eligible": run_result.skipped_judge_case_ids,
        "failed_cases": [
            {
                "case_id": f.case_id,
                "error_type": f.error_type,
                "sanitized_error": f.sanitized_error,
            }
            for f in run_result.failed_judge_cases
        ],
        **aggregate_judge_claims(judge_claims_only),
    }

    return aggregate


if __name__ == "__main__":
    # 実APIを使った本実行のエントリーポイント。
    # ユーザーの承認前にこのスクリプトを直接実行しないこと
    # (README Phase4セクション「実行方法」を参照)。
    from evaluation.report import write_report

    result = run_evaluation()
    aggregate = build_aggregate(result)
    paths = write_report(result, aggregate)
    print(f"Evaluation結果を書き出しました: {paths}")
