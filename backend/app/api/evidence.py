"""Evidence関連のAPIエンドポイント。

- GET /evidence/{id} : Evidence Viewer画面用に、1件のEvidenceの詳細を取得する
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.evidence import Evidence
from app.schemas.evidence import EvidenceDetailRead

router = APIRouter(prefix="/evidence", tags=["evidence"])


@router.get("/{evidence_id}", response_model=EvidenceDetailRead)
def get_evidence(evidence_id: int, db: Session = Depends(get_db)) -> EvidenceDetailRead:
    evidence = db.get(Evidence, evidence_id)
    if evidence is None:
        raise HTTPException(status_code=404, detail="Evidence not found")

    return EvidenceDetailRead(
        id=evidence.id,
        claim=evidence.claim,
        evidence_text=evidence.evidence_text,
        source_title=evidence.source.title,
        source_url=evidence.source.url,
        comparison_id=evidence.comparison_id,
        research_id=evidence.comparison.research_id,
        criterion_label=evidence.comparison.criterion_label,
    )
