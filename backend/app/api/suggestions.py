"""Suggest Points関連のAPIエンドポイント。

- POST /suggest-criteria : Technology A/B/Use Caseから、Geminiが追加/優先
  すべき比較ポイントを提案する(Phase 5C)。

重要な設計上の制約:
- Tavilyは呼ばない。Research/Source/Evidenceのいずれも作らない
  (DBセッションにも依存しない、Depends(get_db)は使わない)。
- Gemini呼び出しは1 operation(内部でmax 2 attemptsのretryはあるが、
  ユーザー操作としては1回のSuggest Points押下 = 1回の提案取得)。
- provider errorは既存のresearch_runner.pyと同じ粒度でsanitizeする
  (生のAPIキー・レスポンス本文は返さない)。research_runner.py自体は
  変更しない(BackgroundTasks向けのstatus=failed処理と、ここでの
  HTTPExceptionは扱う対象が違うため、小さなsanitizeロジックをここに
  複製している)。
"""

from fastapi import APIRouter, HTTPException
from google.genai import errors as genai_errors

from app.schemas.suggestion import (
    CriterionSuggestion,
    SuggestCriteriaRequest,
    SuggestCriteriaResponse,
)
from app.services.llm_client import generate_criteria_suggestions
from app.services.suggestion_service import filter_and_cap_suggestions

router = APIRouter(prefix="/suggest-criteria", tags=["suggestions"])


@router.post("", response_model=SuggestCriteriaResponse)
def suggest_criteria(payload: SuggestCriteriaRequest) -> SuggestCriteriaResponse:
    try:
        result = generate_criteria_suggestions(
            item_a=payload.item_a,
            item_b=payload.item_b,
            goal=payload.goal,
            existing_criteria=payload.existing_criteria,
        )
    except genai_errors.ClientError as exc:
        if exc.code in (401, 403):
            detail = "LLM APIキーが設定されていないか無効です。"
        else:
            detail = f"LLM API呼び出しでエラーが発生しました(status: {exc.code})。"
        raise HTTPException(status_code=502, detail=detail) from exc
    except genai_errors.APIError as exc:
        code = getattr(exc, "code", "unknown")
        raise HTTPException(
            status_code=502,
            detail=f"LLM API呼び出しでエラーが発生しました(status: {code})。",
        ) from exc
    except Exception as exc:  # noqa: BLE001 - Reliability要件: 何が起きても落とさない
        raise HTTPException(
            status_code=502,
            detail=f"比較ポイント候補の生成中に予期しないエラーが発生しました: {exc}",
        ) from exc

    accepted = filter_and_cap_suggestions(
        result.suggestions, existing_criteria=payload.existing_criteria
    )
    return SuggestCriteriaResponse(
        suggestions=[
            CriterionSuggestion(name=item.name, reason=item.reason)
            for item in accepted
        ]
    )
