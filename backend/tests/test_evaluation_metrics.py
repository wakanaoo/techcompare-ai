"""evaluation.metrics のルールベースmetrics計算に関するテスト。

DBを使わず、CaseSnapshot/ComparisonSnapshotを直接組み立てて検証する
(純粋な計算ロジックであることの確認)。
"""

from evaluation.metrics import (
    CaseSnapshot,
    ComparisonSnapshot,
    aggregate_metrics,
    classify_failure,
    compute_case_metrics,
)


def _completed_snapshot(**overrides) -> CaseSnapshot:
    defaults = dict(
        case_id="c-test",
        research_id=1,
        status="completed",
        error_message=None,
        latency_seconds=3.0,
        criteria_requested=2,
        sources_fetched=4,
        sources_cited=3,
        comparisons=[
            ComparisonSnapshot(
                criterion="development_speed",
                winner="item_a",
                item_a_evidence_count=1,
                item_b_evidence_count=1,
            ),
            ComparisonSnapshot(
                criterion="ecosystem",
                winner="item_a",
                item_a_evidence_count=1,
                item_b_evidence_count=0,
            ),
        ],
        recommendation_winner="item_a",
    )
    defaults.update(overrides)
    return CaseSnapshot(**defaults)


def test_completed_case_computes_all_fields():
    snapshot = _completed_snapshot()
    m = compute_case_metrics(snapshot)

    assert m.status == "completed"
    assert m.comparison_completeness is True  # 2件要求 = 2件返却
    assert m.evidence_coverage_rate == 3 / 4  # 4ペア中3ペアにEvidenceあり
    assert m.source_utilization_rate == 3 / 4
    # item_aが2軸とも勝利 -> 多数決item_a、recommendation_winnerもitem_a -> 一貫
    assert m.recommendation_consistent is True


def test_failed_case_skips_completion_only_fields():
    snapshot = _completed_snapshot(
        status="failed",
        error_message="LLM API呼び出しでエラーが発生しました(status: 500)。",
        comparisons=[],
        recommendation_winner=None,
    )
    m = compute_case_metrics(snapshot)

    assert m.status == "failed"
    assert m.comparison_completeness is None
    assert m.evidence_coverage_rate is None
    assert m.recommendation_consistent is None
    # source_utilization_rateもanswer-quality metricsの一つなので、
    # failedケースでは0として混ぜずNoneにする(completedケースのみ算出)。
    assert m.source_utilization_rate is None
    # ただし生のsources_fetched/sources_citedはstatusを問わず保持する
    # (補助指標の計算に使う)。
    assert m.sources_fetched == 4
    assert m.sources_cited == 3


def test_comparison_completeness_false_when_count_mismatches_requested():
    snapshot = _completed_snapshot(criteria_requested=3)  # comparisonsは2件のまま
    m = compute_case_metrics(snapshot)
    assert m.comparison_completeness is False


def test_recommendation_inconsistent_when_winner_disagrees_with_majority():
    snapshot = _completed_snapshot(recommendation_winner="item_b")
    m = compute_case_metrics(snapshot)
    assert m.recommendation_consistent is False


def test_recommendation_consistency_is_none_when_majority_is_tied():
    snapshot = _completed_snapshot(
        comparisons=[
            ComparisonSnapshot("development_speed", "item_a", 1, 1),
            ComparisonSnapshot("ecosystem", "item_b", 1, 1),
        ],
        recommendation_winner="item_a",
    )
    m = compute_case_metrics(snapshot)
    assert m.recommendation_consistent is None  # 拮抗しているのでペナルティなし


def test_source_utilization_is_none_when_no_sources_fetched():
    snapshot = _completed_snapshot(sources_fetched=0, sources_cited=0)
    m = compute_case_metrics(snapshot)
    assert m.source_utilization_rate is None


def test_aggregate_metrics_separates_reliability_and_answer_quality():
    completed = compute_case_metrics(_completed_snapshot(case_id="c1"))
    failed = compute_case_metrics(
        _completed_snapshot(
            case_id="c2",
            status="failed",
            error_message="LLM API呼び出しでエラーが発生しました(status: 429)。",
            comparisons=[],
            recommendation_winner=None,
        )
    )

    aggregate = aggregate_metrics([completed, failed])

    reliability = aggregate["reliability"]
    assert reliability["cases_total"] == 2
    assert reliability["cases_completed"] == 1
    assert reliability["cases_failed"] == 1
    assert reliability["research_completion_rate"] == 0.5
    assert reliability["api_failure_count_by_type"] == {"llm_api_error_429": 1}
    assert reliability["latency_seconds"]["mean"] == 3.0

    answer_quality = aggregate["answer_quality"]
    assert answer_quality["cases_evaluated"] == 1  # completedケースの数のみ
    # answer-quality metricsはすべてcompletedケースのみで計算される。
    assert answer_quality["comparison_completeness_rate"] == 1.0
    assert answer_quality["evidence_coverage_rate_mean"] == 3 / 4
    assert answer_quality["recommendation_consistency_rate"] == 1.0
    # 重要: failedケース(source_utilization_rate=None)は0として混ぜない。
    # completedケース1件(3/4)だけの平均になる。
    assert answer_quality["source_utilization_rate_mean"] == 3 / 4


def test_supplementary_all_cases_metric_is_dragged_down_by_failed_cases():
    """補助指標(all-cases版)は、failedケースを0件として混ぜてよい
    (これは主要指標と明確に分離された参考情報)。"""
    completed = compute_case_metrics(_completed_snapshot(case_id="c1"))
    # sources_fetched=4, sources_cited=0(failedなので引用なし)。
    failed = compute_case_metrics(
        _completed_snapshot(
            case_id="c2", status="failed", sources_cited=0, comparisons=[], recommendation_winner=None
        )
    )

    aggregate = aggregate_metrics([completed, failed])

    # answer_quality(主要指標)はfailedを含めないので3/4のまま。
    assert aggregate["answer_quality"]["source_utilization_rate_mean"] == 3 / 4
    # supplementary(補助指標)はfailedのsource_utilization=0/4=0.0も含めた平均。
    assert aggregate["supplementary"]["source_utilization_rate_mean_all_cases"] == (
        (3 / 4 + 0.0) / 2
    )


def test_classify_failure_extracts_llm_api_error_status_code():
    msg = "LLM API呼び出しでエラーが発生しました(status: 429)。"
    assert classify_failure(msg) == "llm_api_error_429"


def test_classify_failure_distinguishes_search_and_llm_key_errors():
    assert classify_failure("検索APIキーが設定されていないか無効です。") == "search_api_key_error"
    assert classify_failure("LLM APIキーが設定されていないか無効です。") == "llm_api_key_error"


def test_classify_failure_returns_none_for_completed_case():
    assert classify_failure(None) is None


def test_aggregate_metrics_with_empty_list_returns_none_rates():
    aggregate = aggregate_metrics([])
    assert aggregate["reliability"]["cases_total"] == 0
    assert aggregate["reliability"]["research_completion_rate"] is None
    assert aggregate["answer_quality"]["comparison_completeness_rate"] is None
    assert aggregate["supplementary"]["source_utilization_rate_mean_all_cases"] is None
