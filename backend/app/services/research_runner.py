"""BackgroundTasksから呼ばれる、Research 1件分の処理本体。

流れ:
  pending(作成時) -> researching -> completed
                                  -> failed (エラー時、error_messageを保存)

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

from google.genai import errors as genai_errors

from app.db.session import SessionLocal
from app.models.comparison import Comparison
from app.models.research import Research
from app.schemas.criteria import CRITERION_LABELS, Criterion
from app.services.llm_client import generate_comparison
from app.services.llm_schemas import ComparisonReportResult


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


def run_research(research_id: int) -> None:
    db = SessionLocal()
    try:
        research = db.get(Research, research_id)
        if research is None:
            return

        research.status = "researching"
        db.commit()

        try:
            result = generate_comparison(
                item_a=research.item_a,
                item_b=research.item_b,
                goal=research.goal,
                criteria=research.criteria,
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
            db.add(
                Comparison(
                    research_id=research.id,
                    criterion=item.criterion,
                    # criterion_labelはLLMの自由生成に依存せず、backend側の
                    # 固定マスタ(CRITERION_LABELS)から決定する。
                    # (_validate_comparisons_match_criteriaでcriterionの妥当性は
                    # 検証済みのため、ここでCriterion(item.criterion)は必ず成功する)
                    criterion_label=CRITERION_LABELS[Criterion(item.criterion)],
                    item_a_summary=item.item_a_summary,
                    item_b_summary=item.item_b_summary,
                    item_a_score=item.item_a_score,
                    item_b_score=item.item_b_score,
                    winner=item.winner.value,
                )
            )

        research.status = "completed"
        db.commit()
    finally:
        db.close()
