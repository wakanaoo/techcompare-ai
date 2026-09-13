"""Evidence用のPydanticスキーマ(APIの入出力の型定義)。"""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class EvidenceDetailRead(BaseModel):
    """GET /evidence/{id} のレスポンス(Evidence Viewer画面用)。"""

    id: int
    # このEvidenceがitem_a/item_bどちらの技術の主張を裏付けるものか。
    side: Literal["item_a", "item_b"]
    # sideに対応する実際の技術名(例: "FastAPI")。Evidence Viewer側で
    # "item_a"という内部値ではなく実際の技術名を表示するために使う。
    side_label: str
    claim: str
    evidence_text: str
    source_title: str
    source_url: str
    comparison_id: int
    research_id: int
    criterion_label: str

    model_config = ConfigDict(from_attributes=True)
