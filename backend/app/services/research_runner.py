"""BackgroundTasksから呼ばれる、Research 1件分の処理本体。

Phase 3の流れ(2-stage pipeline: 検索 → grounded comparison生成。
LLM呼び出しは1回だけ):
  pending(作成時) -> researching -> completed
                                  -> failed (エラー時、error_messageを保存)

  researching中に行うこと:
    1. Tavily APIで検索し、Sourceとして保存する(Phase 5Dから、
       item_a向け・item_b向け・比較記事向けの3クエリ。criteria/goalを
       反映したうえで、件数はcriteria数に関係なく常に3回)
    2. 保存したSourceを根拠として、Gemini APIを1回呼び出しComparisonを生成する
    3. LLMが挙げた(source_id, chunk_index)を検証し、実在するsource・
       範囲内のchunkにのみEvidenceを関連付ける(evidence_textは、
       backend側で再計算したchunkの実テキストをそのまま使う。Phase 5D)

設計上の注意(README「BackgroundTasksについて」も参照):
FastAPIのBackgroundTasksは、レスポンスを返した後にサーバープロセス内で
実行される簡易的な仕組みであり、durable(永続的)なジョブキューではない。
サーバーが再起動・クラッシュした場合、実行中のResearchはstatusが
pending/researchingのまま止まってしまう。本格的な信頼性が必要になったら
Celery/RQ/クラウドキュー等への置き換えを検討する。

また、この関数はリクエストのDBセッション(Depends(get_db))を使い回さない。
BackgroundTasksはレスポンス送出後に実行されるため、リクエストスコープの
セッションは既にcloseされている可能性があり、ここで新しいセッションを
自分で開閉する。
"""

import logging
import time

import tavily.errors as tavily_errors
from google.genai import errors as genai_errors

from app.db.session import SessionLocal
from app.models.comparison import Comparison
from app.models.evidence import Evidence
from app.models.research import Research
from app.models.source import Source
from app.schemas.criteria import label_for
from app.services.llm_client import generate_comparison
from app.services.llm_schemas import ComparisonReportResult
from app.services.search_client import (
    SearchResultItem,
    build_search_queries,
    get_source_chunks,
    normalize_url,
    search_technology,
)


# Phase 5F: Observability。goal/criteria/Source本文等の自由文・大量テキスト
# はログに出さない(research_id・所要時間・成功失敗・件数のみ)。
# Tavily/Gemini phaseの所要時間は、DBのtimestamp(PostgreSQLのnow()は
# トランザクション開始時刻を返すため、ここでの計測には使えないことが
# Phase 5Eの調査で判明した)ではなく、ここでtime.monotonic()を直接使って
# 計測する。
logger = logging.getLogger(__name__)


class MalformedLLMResponseError(Exception):
    """LLMの応答がリクエストしたcriteriaと一致しない等、内容として不正な場合。"""


def _validate_comparisons_match_criteria(
    result: ComparisonReportResult, criteria: list[str]
) -> None:
    """LLMが返したcomparisonsが、要求したcriteriaと過不足なく一致するか検証する。

    件数・種類のいずれかがズレていたら(余分・欠落・重複)、malformed responseとして
    扱い、DBには保存しない。
    """
    requested = list(criteria)
    returned = [item.criterion for item in result.comparisons]

    if len(returned) != len(requested) or set(returned) != set(requested):
        raise MalformedLLMResponseError(
            f"要求したcriteria {requested} と、LLMが返したcriterion {returned} が"
            "一致しません(件数または種類の不一致)。"
        )


def _fetch_sources(db, research: Research) -> dict[int, SearchResultItem]:
    """Technology × Use Case × Comparison Pointを反映した3クエリで検索し、
    Sourceとして保存する(Phase 5D、Phase 5D-cでクエリの役割分担を変更)。

    criteria件数に関わらず常に3クエリ(item_a向け・item_b向けは英語中心の
    official/primary retrieval用、比較記事向けは日本語のまま、
    build_search_queries()参照)。3クエリ分の結果はURLで重複排除してから
    保存する(Query間で同じURLがヒットすることがあるため)。

    戻り値は {保存後のDB上のsource id: SearchResultItem} の辞書
    (LLMへのプロンプト・後段の検証で、DB上の実IDをそのまま使うため)。
    """
    queries = build_search_queries(
        item_a=research.item_a,
        item_b=research.item_b,
        criteria=research.criteria,
        goal=research.goal,
    )

    found: list[SearchResultItem] = []
    seen_urls: set[str] = set()
    for query in queries:
        for item in search_technology(query, item_a=research.item_a, item_b=research.item_b):
            normalized = normalize_url(item.url)
            if normalized in seen_urls:
                continue
            seen_urls.add(normalized)
            found.append(item)

    sources_by_id: dict[int, SearchResultItem] = {}
    for item in found:
        source = Source(
            research_id=research.id,
            title=item.title,
            url=item.url,
            content=item.content,
        )
        db.add(source)
        db.flush()  # source.idを確定させる(まだcommitはしない)
        sources_by_id[source.id] = item

    return sources_by_id


def run_research(research_id: int) -> None:
    total_start = time.monotonic()
    db = SessionLocal()
    research: Research | None = None
    try:
        research = db.get(Research, research_id)
        if research is None:
            return

        research.status = "researching"
        db.commit()

        # --- Stage 1: Web検索してSourceとして保存する ---
        retrieval_start = time.monotonic()
        try:
            sources_by_id = _fetch_sources(db, research)
            db.commit()
        except (
            tavily_errors.InvalidAPIKeyError,
            tavily_errors.MissingAPIKeyError,
        ):
            db.rollback()
            research.status = "failed"
            research.error_message = "検索APIキーが設定されていないか無効です。"
            db.commit()
            logger.info(
                "research_phase research_id=%d phase=retrieval duration_s=%.2f outcome=failure",
                research_id,
                time.monotonic() - retrieval_start,
            )
            return
        except Exception as exc:  # noqa: BLE001 - Reliability要件: 何が起きても落とさない
            db.rollback()
            research.status = "failed"
            research.error_message = f"Web検索中に予期しないエラーが発生しました: {exc}"
            db.commit()
            logger.info(
                "research_phase research_id=%d phase=retrieval duration_s=%.2f outcome=failure",
                research_id,
                time.monotonic() - retrieval_start,
            )
            return
        logger.info(
            "research_phase research_id=%d phase=retrieval duration_s=%.2f outcome=success "
            "sources_fetched=%d",
            research_id,
            time.monotonic() - retrieval_start,
            len(sources_by_id),
        )

        # --- Stage 2: 保存済みSourceを根拠にLLMを1回呼び出す ---
        comparison_start = time.monotonic()
        try:
            result = generate_comparison(
                item_a=research.item_a,
                item_b=research.item_b,
                goal=research.goal,
                criteria=research.criteria,
                sources=sources_by_id,
            )
        except genai_errors.ClientError as exc:
            # Gemini APIからの生のエラー本文(内部情報を含みうる)はそのまま
            # ユーザーに見せず、HTTPステータスに応じた定型メッセージだけを保存する。
            research.status = "failed"
            if exc.code in (401, 403):
                research.error_message = "LLM APIキーが設定されていないか無効です。"
            else:
                research.error_message = (
                    f"LLM API呼び出しでエラーが発生しました(status: {exc.code})。"
                )
            db.commit()
            logger.info(
                "research_phase research_id=%d phase=comparison_generation duration_s=%.2f "
                "outcome=failure",
                research_id,
                time.monotonic() - comparison_start,
            )
            return
        except genai_errors.APIError as exc:
            research.status = "failed"
            code = getattr(exc, "code", "unknown")
            research.error_message = (
                f"LLM API呼び出しでエラーが発生しました(status: {code})。"
            )
            db.commit()
            logger.info(
                "research_phase research_id=%d phase=comparison_generation duration_s=%.2f "
                "outcome=failure",
                research_id,
                time.monotonic() - comparison_start,
            )
            return
        except Exception as exc:  # noqa: BLE001 - Reliability要件: 何が起きても落とさない
            research.status = "failed"
            research.error_message = f"比較生成中に予期しないエラーが発生しました: {exc}"
            db.commit()
            logger.info(
                "research_phase research_id=%d phase=comparison_generation duration_s=%.2f "
                "outcome=failure",
                research_id,
                time.monotonic() - comparison_start,
            )
            return
        logger.info(
            "research_phase research_id=%d phase=comparison_generation duration_s=%.2f "
            "outcome=success",
            research_id,
            time.monotonic() - comparison_start,
        )

        try:
            _validate_comparisons_match_criteria(result, research.criteria)
        except MalformedLLMResponseError as exc:
            research.status = "failed"
            research.error_message = f"比較生成中に予期しないエラーが発生しました: {exc}"
            db.commit()
            return

        research.recommendation_winner = result.recommendation.winner.value
        research.recommendation_summary = result.recommendation.summary
        research.recommendation_reason = result.recommendation.reason

        for item in result.comparisons:
            comparison = Comparison(
                research_id=research.id,
                criterion=item.criterion,
                # criterion_labelはLLMの自由生成に依存せず、backend側で決定する。
                # 固定候補ならCRITERION_LABELSの日本語ラベル、自由入力の
                # criterionならその文字列自体をラベルとして使う(label_for参照)。
                criterion_label=label_for(item.criterion),
                item_a_summary=item.item_a_summary,
                item_b_summary=item.item_b_summary,
                item_a_score=item.item_a_score,
                item_b_score=item.item_b_score,
                winner=item.winner.value,
            )
            db.add(comparison)
            db.flush()  # comparison.idを確定させる

            for side, side_label, citations in (
                ("item_a", research.item_a, item.item_a_citations),
                ("item_b", research.item_b, item.item_b_citations),
            ):
                for citation in citations:
                    source_item = sources_by_id.get(citation.source_id)
                    if source_item is None:
                        # LLMが実在しないsource_idを挙げた場合は、Evidenceを
                        # 作らずに無視する(勝手にsourceを関連付けない)。
                        continue

                    # LLMが書いたchunk本文は一切信用せず、backend側で
                    # 同じ入力から再計算したchunkの実テキストだけを使う
                    # (verbatimであることを保証するため)。
                    chunks = get_source_chunks(source_item.content)
                    if not (0 <= citation.chunk_index < len(chunks)):
                        # 範囲外のchunk_indexも同様に無視する。
                        continue
                    excerpt = chunks[citation.chunk_index]

                    db.add(
                        Evidence(
                            comparison_id=comparison.id,
                            source_id=citation.source_id,
                            # sideは、今このループがitem_a/item_bどちらを
                            # 処理しているかを明示的に渡す(claim文字列の
                            # パースには依存しない)。
                            side=side,
                            claim=f"{side_label}の{label_for(item.criterion)}について",
                            # 根拠本文はLLMに生成させず、Source.contentから
                            # 再計算したchunkをそのまま複製する(Phase 5D:
                            # Source全文ではなく、claimを実際に支える
                            # verbatim excerptのみを保存する)。
                            evidence_text=excerpt,
                        )
                    )

        research.status = "completed"
        db.commit()
    finally:
        final_status = research.status if research is not None else "not_found"
        logger.info(
            "research_done research_id=%d status=%s total_duration_s=%.2f",
            research_id,
            final_status,
            time.monotonic() - total_start,
        )
        db.close()
