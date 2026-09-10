"""ルールベースmetrics: DBに保存された結果(Research/Comparison/Evidence/Source)
だけから機械的に計算できる指標。

LLMの生の出力(不正なsource_idを何個生成したか等)には依存しない。
`run_research()`が実際にDBへ保存した「結果」だけを見て評価する
(README Phase4セクションの設計意図を参照)。

Phase 4.1: metricsを2種類に明確に分ける(Full Evaluation Run #1で、
失敗ケースがSource Utilization等の品質指標に0として混入していたことを
受けた整理)。
  - Reliability metrics: パイプラインが完走したかどうかを測る指標。
    分母は「実行した全ケース」(失敗も含む)。
  - Answer-quality metrics: 完走した結果の中身の質を測る指標。
    分母は「completedしたケース」(または、その中でも判定可能なケース)
    のみ。failed Researchは0として混ぜない。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from statistics import mean, median


@dataclass(frozen=True)
class ComparisonSnapshot:
    """1つの比較軸(Comparison 1行)についての、評価に必要な情報だけを持つ値。"""

    criterion: str
    winner: str  # "item_a" | "item_b" | "tie"
    item_a_evidence_count: int
    item_b_evidence_count: int


@dataclass(frozen=True)
class CaseSnapshot:
    """Evaluation 1ケース分の実行結果(DBから読み出した後の値)。"""

    case_id: str
    research_id: int | None
    status: str  # "completed" | "failed" | それ以外(想定外)
    error_message: str | None
    latency_seconds: float | None
    criteria_requested: int
    sources_fetched: int
    sources_cited: int
    comparisons: list[ComparisonSnapshot] = field(default_factory=list)
    recommendation_winner: str | None = None


@dataclass(frozen=True)
class CaseMetrics:
    case_id: str
    status: str
    error_message: str | None
    latency_seconds: float | None
    # sources_fetched/sources_citedは単なる実測件数であり、failedケースでも
    # 意味を持つ(0件のこともある)ため、statusを問わずそのまま保持する。
    # 補助指標(supplementary)の計算に使う。
    sources_fetched: int
    sources_cited: int
    # 以下はすべて「completedケースのみ」算出する(answer-quality metrics)。
    # failedケースはNoneのままにし、0として品質平均に混ぜない。
    comparison_completeness: bool | None
    evidence_coverage_rate: float | None  # pairs_with_evidence / pairs_total
    source_utilization_rate: float | None  # sources_cited / sources_fetched(completedのみ)
    recommendation_consistent: bool | None


def compute_case_metrics(snapshot: CaseSnapshot) -> CaseMetrics:
    is_completed = snapshot.status == "completed"

    comparison_completeness = None
    evidence_coverage_rate = None
    source_utilization_rate = None
    recommendation_consistent = None

    if is_completed:
        comparison_completeness = len(snapshot.comparisons) == snapshot.criteria_requested

        pairs_total = len(snapshot.comparisons) * 2
        if pairs_total > 0:
            pairs_with_evidence = sum(
                1 for c in snapshot.comparisons if c.item_a_evidence_count > 0
            ) + sum(1 for c in snapshot.comparisons if c.item_b_evidence_count > 0)
            evidence_coverage_rate = pairs_with_evidence / pairs_total

        # Source Utilizationも「completedケースの中身の質」を測るanswer-quality
        # metricsの一つなので、failedケース(比較生成に届かず0件のまま)を
        # 0として混ぜないよう、is_completed配下でのみ算出する。
        if snapshot.sources_fetched > 0:
            source_utilization_rate = snapshot.sources_cited / snapshot.sources_fetched

        recommendation_consistent = _is_recommendation_consistent(snapshot)

    return CaseMetrics(
        case_id=snapshot.case_id,
        status=snapshot.status,
        error_message=snapshot.error_message,
        latency_seconds=snapshot.latency_seconds,
        sources_fetched=snapshot.sources_fetched,
        sources_cited=snapshot.sources_cited,
        comparison_completeness=comparison_completeness,
        evidence_coverage_rate=evidence_coverage_rate,
        source_utilization_rate=source_utilization_rate,
        recommendation_consistent=recommendation_consistent,
    )


def _is_recommendation_consistent(snapshot: CaseSnapshot) -> bool | None:
    """各criterionのComparison.winnerを多数決した結果と、
    Research.recommendation_winnerが矛盾していないかを判定する。

    多数決が拮抗している(例: 2軸ずつでitem_a/item_bが同数勝利)場合は、
    どちらのrecommendationも不自然ではないため判定対象外(None)として
    ペナルティを課さない。
    """
    count_a = sum(1 for c in snapshot.comparisons if c.winner == "item_a")
    count_b = sum(1 for c in snapshot.comparisons if c.winner == "item_b")

    if count_a == count_b:
        return None

    majority = "item_a" if count_a > count_b else "item_b"
    return snapshot.recommendation_winner == majority


# --- API failure分類(reliability metrics用) ---
# research_runner.py(app/、未変更)が保存するerror_messageの定型文から、
# 「どの段階の、どんな種類の失敗か」を分類する。app/側のロジックには
# 依存せず、あくまで保存済みの文字列を読むだけ。
_LLM_STATUS_RE = re.compile(r"status:\s*(\d+)")


def classify_failure(error_message: str | None) -> str | None:
    """failedケースのerror_messageを、集計しやすいtype文字列に分類する。
    completedケース(error_message=None)はNoneを返す。
    """
    if error_message is None:
        return None
    if error_message.startswith("検索APIキーが設定されていないか無効です"):
        return "search_api_key_error"
    if error_message.startswith("Web検索中に予期しないエラーが発生しました"):
        return "search_unexpected_error"
    if error_message.startswith("LLM APIキーが設定されていないか無効です"):
        return "llm_api_key_error"
    if error_message.startswith("LLM API呼び出しでエラーが発生しました"):
        match = _LLM_STATUS_RE.search(error_message)
        return f"llm_api_error_{match.group(1)}" if match else "llm_api_error_unknown"
    if error_message.startswith("比較生成中に予期しないエラーが発生しました"):
        return "llm_unexpected_error"
    return "other"


def aggregate_metrics(case_metrics: list[CaseMetrics]) -> dict:
    """Reliability metricsとAnswer-quality metricsを明確に分けて返す。

    - reliability: 分母は全ケース。パイプラインが完走したか/なぜ失敗したか/
      レイテンシ、を測る。
    - answer_quality: 分母はcompletedケース(またはその中でも判定可能な
      ケース)のみ。failedケースは0として混ぜない。
    - supplementary: 主要指標と明確に区別した補助指標。all-cases版が
      必要な場合はここに置く(例: Source Utilizationのfailed込み平均。
      Full Evaluation Run #1ではこれが主指標に混入していたバグがあった)。
    """
    total = len(case_metrics)
    completed = [m for m in case_metrics if m.status == "completed"]
    failed = [m for m in case_metrics if m.status != "completed"]

    def _rate(values: list[bool]) -> float | None:
        return (sum(1 for v in values if v) / len(values)) if values else None

    def _mean_of(values: list[float]) -> float | None:
        return mean(values) if values else None

    latencies = [m.latency_seconds for m in case_metrics if m.latency_seconds is not None]

    failure_counts: dict[str, int] = {}
    for m in failed:
        failure_type = classify_failure(m.error_message) or "other"
        failure_counts[failure_type] = failure_counts.get(failure_type, 0) + 1

    reliability = {
        "cases_total": total,
        "cases_completed": len(completed),
        "cases_failed": len(failed),
        "research_completion_rate": len(completed) / total if total else None,
        "api_failure_count_by_type": failure_counts,
        "latency_seconds": {
            "mean": _mean_of(latencies),
            "p50": median(latencies) if latencies else None,
            "max": max(latencies) if latencies else None,
        },
    }

    completeness_values = [
        m.comparison_completeness
        for m in completed
        if m.comparison_completeness is not None
    ]
    evidence_rates = [
        m.evidence_coverage_rate for m in completed if m.evidence_coverage_rate is not None
    ]
    source_rates_completed_only = [
        m.source_utilization_rate for m in completed if m.source_utilization_rate is not None
    ]
    consistency_values = [
        m.recommendation_consistent
        for m in completed
        if m.recommendation_consistent is not None
    ]

    answer_quality = {
        "cases_evaluated": len(completed),
        "comparison_completeness_rate": _rate(completeness_values),
        "evidence_coverage_rate_mean": _mean_of(evidence_rates),
        "source_utilization_rate_mean": _mean_of(source_rates_completed_only),
        "recommendation_consistency_rate": _rate(consistency_values),
    }

    # 補助指標: source_utilizationのfailed込み(0件なら0として扱う)all-cases版。
    # 主要指標(answer_quality、completedのみ)とは明確に分離し、参考情報として残す。
    # Full Evaluation Run #1では、この計算が誤って主指標側に混入していた
    # (failed Researchが0として品質平均を押し下げていた)。
    source_rates_all_cases = [
        m.sources_cited / m.sources_fetched for m in case_metrics if m.sources_fetched > 0
    ]
    supplementary = {
        "source_utilization_rate_mean_all_cases": _mean_of(source_rates_all_cases),
    }

    return {
        "reliability": reliability,
        "answer_quality": answer_quality,
        "supplementary": supplementary,
    }
