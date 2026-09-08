"""BackgroundTasksから呼ばれる、Research 1件分の処理本体。

Phase 3の流れ(2-stage pipeline: 検索 → grounded comparison生成。
LLM呼び出しは1回だけ):
  pending(作成時) -> researching -> completed
                                  -> failed (エラー時、error_messageを保存)

  researching中に行うこと:
    1. Tavily APIでitem_a / item_bそれぞれを検索し、Sourceとして保存する
    2. 保存したSourceを根拠として、Gemini APIを1回呼び出しComparisonを生成する
    3. LLMが挙げたsource_idを検証し、実在するsourceにのみEvidenceを関連付ける

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

import tavily.errors as tavily_errors
from google.genai import errors as genai_errors

from app.db.session import SessionLocal
from app.models.comparison import Comparison
from app.models.evidence import Evidence
from app.models.research import Research
from app.models.source import Source
from app.schemas.criteria import CRITERION_LABELS, Criterion
from app.services.llm_client import generate_comparison
from app.services.llm_schemas import ComparisonReportResult
from app.services.search_client import SearchResultItem, search_technology


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
    """item_a/item_bについてWeb検索し、Sourceとして保存する。

    戻り値は {保存後のDB上のsource id: SearchResultItem} の辞書
    (LLMへのプロンプト・後段の検証で、DB上の実IDをそのまま使うため)。
    """
    found: list[SearchResultItem] = []
    found.extend(search_technology(research.item_a))
    found.extend(search_technology(research.item_b))

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
    db = SessionLocal()
    try:
        research = db.get(Research, research_id)
        if research is None:
            return

        research.status = "researching"
        db.commit()

        # --- Stage 1: Web検索してSourceとして保存する ---
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
            return
        except Exception as exc:  # noqa: BLE001 - Reliability要件: 何が起きても落とさない
            db.rollback()
            research.status = "failed"
            research.error_message = f"Web検索中に予期しないエラーが発生しました: {exc}"
            db.commit()
            return

        # --- Stage 2: 保存済みSourceを根拠にLLMを1回呼び出す ---
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
            return
        except genai_errors.APIError as exc:
            research.status = "failed"
            code = getattr(exc, "code", "unknown")
            research.error_message = (
                f"LLM API呼び出しでエラーが発生しました(status: {code})。"
            )
            db.commit()
            return
        except Exception as exc:  # noqa: BLE001 - Reliability要件: 何が起きても落とさない
            research.status = "failed"
            research.error_message = f"比較生成中に予期しないエラーが発生しました: {exc}"
            db.commit()
            return

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
                # criterion_labelはLLMの自由生成に依存せず、backend側の
                # 固定マスタ(CRITERION_LABELS)から決定する。
                criterion_label=CRITERION_LABELS[Criterion(item.criterion)],
                item_a_summary=item.item_a_summary,
                item_b_summary=item.item_b_summary,
                item_a_score=item.item_a_score,
                item_b_score=item.item_b_score,
                winner=item.winner.value,
            )
            db.add(comparison)
            db.flush()  # comparison.idを確定させる

            for side_label, cited_ids in (
                (research.item_a, item.item_a_source_ids),
                (research.item_b, item.item_b_source_ids),
            ):
                for source_id in cited_ids:
                    source_item = sources_by_id.get(source_id)
                    if source_item is None:
                        # LLMが実在しないIDを挙げた場合は、Evidenceを
                        # 作らずに無視する(勝手にsourceを関連付けない)。
                        continue
                    db.add(
                        Evidence(
                            comparison_id=comparison.id,
                            source_id=source_id,
                            claim=f"{side_label}の{CRITERION_LABELS[Criterion(item.criterion)]}について",
                            # 根拠本文はLLMに生成させず、Tavilyが実際に
                            # 取得したSource.contentをそのまま複製する。
                            evidence_text=source_item.content,
                        )
                    )

        research.status = "completed"
        db.commit()
    finally:
        db.close()
