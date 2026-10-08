"""Phase 4 Evaluation本体: 固定Evaluation Set(既定15件)を、本番と同じ
`app.services.research_runner.run_research()` に通し、
  - 全ケースについてルールベースmetricsを算出
  - 代表ケース(既定5件)についてLLM Judgeでsemantic metricsを算出
した結果をまとめて返す。

`run_research()` / `generate_comparison()` 等の本番コードは一切変更しない。
Gemini/Tavilyの実際の呼び出し回数・token使用量は
`evaluation.usage_capture` の薄いラッパーで計測する。

Phase 5G: 複数日に分けた実行(resume)について
Free Tierの日次上限(RPD)が、固定15ケースのcomparison + Judge最大5ケースで
ちょうど使い切る設計になっており、retryの余地が無いことが判明した
(README/事後調査参照)。`run_evaluation()`(1プロセスで15件+Judgeを
一度に実行する既存の経路)はテスト・小規模dry run用に変更せず残しつつ、
以下を新設する:
  - `run_stage_a_cases()`: 指定ケースのうち、`resume_state.ResumeState`上で
    まだ一度も試行していない(unattempted)ケースだけについてStage A
    (comparison生成)を実行し、実行結果(research_id・status・実測usage)を
    stateへ逐次保存する。completed/failedのいずれもterminalとして扱い
    再実行しない(試行済みケースを誤って再実行してRPDを浪費しない、かつ
    failed caseを後日成功するまでやり直してCompletion Rateを人工的に
    改善させない、という2つの理由による)。
  - `collect_stage_a_results()`: stateに記録済みのresearch_idから、
    DBに保存済みの結果を再構築する(再度Tavily/Geminiを呼ばない)。
  - `sum_stage_a_usage_from_state()`: 複数日に分けて実行されたcase群の
    実測usageを、state(ファイル)から合算する(メモリ上のUsageRecorderは
    プロセスをまたげないため)。
  - `_run_judge_stage()`: 既存`run_evaluation()`のStage B部分を切り出した
    もので、Stage Aの完成した結果(`case_results`)さえあれば、
    Stage Aを実行したプロセス/日と独立して呼び出せる。

いずれも本番コード(`app/`配下)は一切変更しない。新規のDBテーブル・
ジョブキューは追加しない(`evaluation.resume_state`参照)。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from google.genai import errors as genai_errors

from app.db.session import SessionLocal
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
from evaluation.resume_state import CaseState, ResumeState
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
            # Evidence.sideは構造化された列(Phase 5B)なので、claim文字列の
            # パースには依存せずそのまま使う。
            a_evidences = [e for e in comp.evidences if e.side == "item_a"]
            b_evidences = [e for e in comp.evidences if e.side == "item_b"]
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


def _run_judge_stage(
    case_results: list[CaseRunResult],
    target_judge_ids: list[str],
) -> tuple[list[str], list[str], list[JudgeFailure], list[tuple[str, ClaimJudgment]]]:
    """Stage B: 指定ケースについてLLM Judgeを実行する。

    `run_evaluation()`(1プロセスで一括実行)と、`run_stage_b_judge_and_report()`
    (Stage Aと別日/別プロセスで実行)の両方から共有される(Phase 5G切り出し。
    ロジック自体は変更していない)。

    1ケースのJudge失敗(一時的なAPIエラー等)でEvaluation全体を止めない。
    Stage Aで既に成功しているルールベースmetricsは、Judgeの成否に関わらず
    必ず保持し、最後まで処理を進めてレポートを生成できるようにする。
    """
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

    return judged_case_ids, skipped_judge_case_ids, failed_judge_cases, judged_claims


def run_evaluation(
    cases: list[EvaluationCase] | None = None,
    judge_case_ids: list[str] | None = None,
) -> EvaluationRunResult:
    """Evaluation Set全件を実行し、結果をまとめて返す。

    cases / judge_case_idsを指定しない場合は、`dataset.py`の既定値
    (15件・代表5件)を使う。実APIの呼び出し回数を絞ったdry runをしたい
    場合は、casesにEVALUATION_CASESの一部だけを渡せばよい。

    Free Tierの日次上限(RPD)に収まらない本番相当の実行(固定15件+Judge
    5件)を複数日に分けたい場合は、代わりに`run_stage_a_cases()`と
    `run_stage_b_judge_and_report()`(resumeに対応)を使うこと。
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
        judged_case_ids, skipped_judge_case_ids, failed_judge_cases, judged_claims = (
            _run_judge_stage(case_results, target_judge_ids)
        )

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


# --- Phase 5G: 複数日に分けた実行(resume) ----------------------------------


def run_stage_a_cases(
    cases: list[EvaluationCase],
    state: ResumeState,
) -> None:
    """指定されたcasesのうち、stateで既に試行済み(completed/failedいずれか、
    = `state.attempted_case_ids()`に含まれる)のcaseはスキップし、
    まだ一度も試行していない(unattempted)caseだけについて本番
    run_research()を実行する。

    重要: failedも「もう一度試行すれば成功するかもしれない」ものとしては
    扱わない(resumeを「最終的に成功させる」仕組みにしない)。このEvaluationで
    測りたいReliabilityは「各固定caseを、その時点の同一条件で1回評価した
    結果」であり、1 case内の最大3 attempts(既存のrequestレベルのretry、
    変更しない)を使い切ってfailedになったcaseを翌日以降に再実行すると、
    Completion Rateが人工的に改善し、Run #2 / Phase 5E / Phase 5Fとの比較が
    不公平になる。そのためcompleted/failedはいずれもterminal(確定した
    最終結果)として扱い、再実行しない。resumeの目的は「日次RPD制限のため、
    まだ評価していないcaseを翌日に続ける」ことに限定する。

    Tavily/Geminiへの実呼び出しは、まだ一度も試行していないcaseに対して
    のみ発生する(試行済みcaseを誤って再実行し、RPD予算を浪費しないように
    する、というのがこの関数の主目的)。1ケース実行するごとにstate.save()
    するので、途中でプロセスが落ちても(RPD上限に達して429が出続ける等)、
    そこまでの進捗は失われない。
    """
    already_attempted = state.attempted_case_ids()
    for case in cases:
        if case.case_id in already_attempted:
            continue

        case_recorder = UsageRecorder()
        with capture_gemini_usage(case_recorder), count_search_calls(case_recorder):
            research_id = _create_pending_research(case)
            run_research(research_id)

        result = _load_case_result(case, research_id)
        usage = sum_usage(case_recorder.gemini_calls)
        state.record_case(
            case.case_id,
            CaseState(
                status=result.snapshot.status,
                research_id=research_id,
                gemini_call_count=usage["call_count"],
                gemini_prompt_tokens=usage["prompt_token_count"],
                gemini_candidates_tokens=usage["candidates_token_count"],
                gemini_total_tokens=usage["total_token_count"],
                tavily_call_count=case_recorder.search_call_count,
            ),
        )
        state.save()


def collect_stage_a_results(
    cases: list[EvaluationCase], state: ResumeState
) -> list[CaseRunResult]:
    """stateに記録済みのresearch_idから、DBに保存済みの結果を再構築する
    (再度Tavily/Geminiを呼ばない)。stateにまだ記録が無いcaseはスキップする
    (呼び出し側で「全件揃っているか」を別途確認すること。例:
    `run_stage_b_judge_and_report()`)。
    """
    results = []
    for case in cases:
        case_state = state.stage_a.get(case.case_id)
        if case_state is None:
            continue
        results.append(_load_case_result(case, case_state.research_id))
    return results


def sum_stage_a_usage_from_state(state: ResumeState) -> tuple[dict, int]:
    """複数日に分けて実行されたcase群の実測Gemini usageとTavily呼び出し回数を、
    state(ファイル)に保存済みの値から合算する。

    各caseは別プロセス/別日に実行されている可能性があり、メモリ上の
    UsageRecorderはプロセスをまたげないため、このファイルの実測値を
    正本として使う(run_stage_a_cases()が1ケースごとに記録している)。
    """
    call_count = sum(s.gemini_call_count for s in state.stage_a.values())
    prompt = sum(s.gemini_prompt_tokens for s in state.stage_a.values())
    candidates = sum(s.gemini_candidates_tokens for s in state.stage_a.values())
    total = sum(s.gemini_total_tokens for s in state.stage_a.values())
    tavily_call_count = sum(s.tavily_call_count for s in state.stage_a.values())

    gemini_comparison_usage = {
        "call_count": call_count,
        "prompt_token_count": prompt,
        "candidates_token_count": candidates,
        "total_token_count": total,
    }
    return gemini_comparison_usage, tavily_call_count


def run_stage_b_judge_and_report(
    state: ResumeState,
    all_cases: list[EvaluationCase] | None = None,
    judge_case_ids: list[str] | None = None,
    out_dir=None,
) -> dict[str, str]:
    """Stage A(全ケース)が完了済みのstateに対してJudgeを実行し、従来と
    同じ形式(JSON + CSV x2)のレポートを書き出す。

    Stage Aを実行したプロセス/日とは独立して呼び出せる(DBとstateファイルだけ
    から結果を再構築するため、Tavily/Geminiはこの関数内ではJudge以外呼ばない)。

    all_casesの全case_idがstateに記録されていない(=まだ一度も実行を
    試みていないcaseがある)場合はRuntimeErrorを送出する。「completed」までは
    要求しない(429/503等で最終的にfailedになったcaseが残っているのは
    正常なState Aの結果であり、既存のReliability metricsの対象でもあるため)。

    out_dir: write_report()にそのまま渡す(省略時は従来どおり
    `evaluation/results/`。テストではtmp_pathを渡して本物の結果ディレクトリを
    汚さないようにする)。
    """
    target_cases = all_cases if all_cases is not None else EVALUATION_CASES
    target_judge_ids = judge_case_ids if judge_case_ids is not None else JUDGE_SAMPLE_CASE_IDS

    missing = [c.case_id for c in target_cases if c.case_id not in state.attempted_case_ids()]
    if missing:
        raise RuntimeError(
            "Stage Aが未実行のcaseが残っています(run_stage_a_casesを先に実行してください): "
            + ", ".join(missing)
        )

    case_results = collect_stage_a_results(target_cases, state)
    gemini_comparison_usage, tavily_call_count = sum_stage_a_usage_from_state(state)

    judge_recorder = UsageRecorder()
    with capture_gemini_usage(judge_recorder):
        judged_case_ids, skipped_judge_case_ids, failed_judge_cases, judged_claims = (
            _run_judge_stage(case_results, target_judge_ids)
        )
    gemini_judge_usage = sum_usage(judge_recorder.gemini_calls)

    run_result = EvaluationRunResult(
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
        tavily_call_count=tavily_call_count,
    )

    from evaluation.report import write_report  # 循環import回避のため関数内でimport

    aggregate = build_aggregate(run_result)
    return write_report(run_result, aggregate, out_dir=out_dir)


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


def _parse_case_ids_arg(raw: str | None) -> list[str] | None:
    if raw is None:
        return None
    return [c.strip() for c in raw.split(",") if c.strip()]


def _main() -> None:
    """実APIを使った本実行のエントリーポイント。
    ユーザーの承認前にこのスクリプトを直接実行しないこと
    (README Phase4セクション「実行方法」を参照)。

    Phase 5G: Free Tierの日次上限(RPD)が固定15ケース+Judge5ケースで
    ちょうど使い切る設計だったため、`--stage`で複数日に分けて実行できる
    ようにした(README/事後調査参照)。

    - 引数無し(従来どおり): 固定15件+Judgeを1プロセスで一括実行する
      (dry runや、RPD上限を気にしない環境向け。挙動は変更していない)。
    - `--run-id RUN_ID --stage comparison [--cases c01,c02,...]`:
      Stage Aのうち、まだ一度も試行していない(unattempted)caseだけを実行し、
      `evaluation/results/resume_state/RUN_ID.json` に進捗を保存する。
      completed/failedいずれも再実行しない(terminal)。
      `--cases`省略時は、まだunattemptedな全15ケースが対象になる。
    - `--run-id RUN_ID --stage judge [--judge-cases c01,...]`:
      既存のstateから全15ケース分のStage A結果を読み込み、Judgeを実行して
      最終的なレポート(JSON + CSV x2、従来と同じ形式)を書き出す。
      全15ケースがstateに記録されていない場合はエラーになる。
    """
    import argparse
    import logging

    from evaluation.report import write_report

    # Phase 5F: Observability。この本実行スクリプトでのみログをコンソールに
    # 出す(pytest実行時・APIサーバー実行時には影響しない、スクリプト単体の
    # ローカル設定)。app.services.llm_client/research_runner、
    # evaluation.judgeが出すログ(gemini_request/research_phase/
    # research_done)がここで見えるようになる。
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-id",
        default=None,
        help="複数日に分けて実行する際にStage A/Judgeを束ねる識別子。"
        "省略時は従来どおり1プロセスで一括実行する(--stageも無視される)。",
    )
    parser.add_argument("--stage", choices=["comparison", "judge"], default=None)
    parser.add_argument(
        "--cases",
        default=None,
        help="(--stage comparison用)実行対象のcase_idをカンマ区切りで指定。"
        "省略時はまだunattemptedな全ケースが対象(completed/failedは再実行しない)。",
    )
    parser.add_argument(
        "--judge-cases",
        default=None,
        help="(--stage judge用)Judge対象のcase_idをカンマ区切りで指定。"
        "省略時はdataset.JUDGE_SAMPLE_CASE_IDS(既定5件)。",
    )
    args = parser.parse_args()

    if args.run_id is None:
        # 従来どおり: 1プロセスで固定15件+Judgeを一括実行する。
        result = run_evaluation()
        aggregate = build_aggregate(result)
        paths = write_report(result, aggregate)
        print(f"Evaluation結果を書き出しました: {paths}")
        return

    if args.stage is None:
        parser.error("--run-idを指定する場合は--stageも指定してください。")

    from evaluation.resume_state import load as load_resume_state

    state = load_resume_state(args.run_id)

    if args.stage == "comparison":
        requested_ids = _parse_case_ids_arg(args.cases)
        if requested_ids is None:
            target_cases = EVALUATION_CASES
        else:
            from evaluation.dataset import get_case_by_id

            target_cases = [get_case_by_id(cid) for cid in requested_ids]

        run_stage_a_cases(target_cases, state)

        done = state.completed_case_ids()
        attempted = state.attempted_case_ids()
        all_ids = {c.case_id for c in EVALUATION_CASES}
        print(
            f"run_id={args.run_id}: comparison完了={len(done)}/{len(all_ids)}件 "
            f"(試行済み={len(attempted)}件、未着手={sorted(all_ids - attempted)})"
        )
        return

    # args.stage == "judge"
    judge_case_ids = _parse_case_ids_arg(args.judge_cases)
    paths = run_stage_b_judge_and_report(state, judge_case_ids=judge_case_ids)
    print(f"Evaluation結果を書き出しました: {paths}")


if __name__ == "__main__":
    _main()
