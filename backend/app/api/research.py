"""Research関連のAPIエンドポイント。

- POST /research             : 新しいResearchを作成し、裏でLLM比較処理を開始する
- GET  /research/{id}        : Researchのstatus等を取得する(polling用の軽量API)
- GET  /research/{id}/result : 完了したResearchの比較結果を取得する
"""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.research import Research
from app.schemas.research import (
    ComparisonRead,
    RecommendationRead,
    ResearchCreate,
    ResearchRead,
    ResearchResultRead,
)
from app.services.research_runner import run_research

router = APIRouter(prefix="/research", tags=["research"])


@router.post("", response_model=ResearchRead, status_code=201)
def create_research(
    payload: ResearchCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> Research:
    """新しいResearchをDBに保存し、比較処理をBackgroundTasksに登録する。

    レスポンスはすぐに返す(status=pending)。実際のLLM呼び出しはこの後、
    裏側(run_research)で進む。
    """
    research = Research(
        item_a=payload.item_a,
        item_b=payload.item_b,
        goal=payload.goal,
        criteria=[c.value for c in payload.criteria],
        status="pending",
    )
    db.add(research)
    db.commit()
    db.refresh(research)

    background_tasks.add_task(run_research, research.id)

    return research


@router.get("/{research_id}", response_model=ResearchRead)
def get_research(research_id: int, db: Session = Depends(get_db)) -> Research:
    """指定したIDのResearchを取得する(GET = 読み取りのみ、副作用なし)。"""
    research = db.get(Research, research_id)
    if research is None:
        raise HTTPException(status_code=404, detail="Research not found")
    return research


@router.get("/{research_id}/result", response_model=ResearchResultRead)
def get_research_result(research_id: int, db: Session = Depends(get_db)) -> ResearchResultRead:
    """完了したResearchの比較結果(Recommendation + 比較表)を取得する。"""
    research = db.get(Research, research_id)
    if research is None:
        raise HTTPException(status_code=404, detail="Research not found")

    if research.status == "failed":
        raise HTTPException(
            status_code=422,
            detail=research.error_message or "Research processing failed",
        )

    if research.status != "completed":
        raise HTTPException(
            status_code=409,
            detail=f"Research is not completed yet (status: {research.status})",
        )

    return ResearchResultRead(
        research_id=research.id,
        item_a=research.item_a,
        item_b=research.item_b,
        goal=research.goal,
        recommendation=RecommendationRead(
            winner=research.recommendation_winner,
            summary=research.recommendation_summary,
            reason=research.recommendation_reason,
        ),
        comparisons=[
            ComparisonRead.model_validate(c) for c in research.comparisons
        ],
    )
