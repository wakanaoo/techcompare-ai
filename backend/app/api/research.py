"""Research関連のAPIエンドポイント。

Phase 1で実装するのは以下の2つだけ:
- POST /research      : 新しいResearchを作成する
- GET  /research/{id} : 指定したResearchを取得する

比較生成・LLM呼び出し・Web検索などはまだ行わない。
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.research import Research
from app.schemas.research import ResearchCreate, ResearchRead

router = APIRouter(prefix="/research", tags=["research"])


@router.post("", response_model=ResearchRead, status_code=201)
def create_research(payload: ResearchCreate, db: Session = Depends(get_db)) -> Research:
    """新しいResearchをDBに保存する(POST = 新規作成)。"""
    research = Research(
        item_a=payload.item_a,
        item_b=payload.item_b,
        goal=payload.goal,
        status="pending",
    )
    db.add(research)
    db.commit()
    db.refresh(research)
    return research


@router.get("/{research_id}", response_model=ResearchRead)
def get_research(research_id: int, db: Session = Depends(get_db)) -> Research:
    """指定したIDのResearchを取得する(GET = 読み取りのみ、副作用なし)。"""
    research = db.get(Research, research_id)
    if research is None:
        raise HTTPException(status_code=404, detail="Research not found")
    return research
