"""Evidence用のPydanticスキーマ(APIの入出力の型定義)。"""

from pydantic import BaseModel, ConfigDict


class EvidenceDetailRead(BaseModel):
    """GET /evidence/{id} のレスポンス(Evidence Viewer画面用)。"""

    id: int
    claim: str
    evidence_text: str
    source_title: str
    source_url: str
    comparison_id: int
    research_id: int
    criterion_label: str

    model_config = ConfigDict(from_attributes=True)
