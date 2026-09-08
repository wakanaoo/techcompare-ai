"""FastAPIアプリのエントリーポイント。"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.evidence import router as evidence_router
from app.api.research import router as research_router
from app.core.config import settings
from app.db.session import Base, engine

# モデルをBase.metadata に登録するためimportしておく(直接は使わない)。
from app.models import comparison as _comparison_model  # noqa: F401
from app.models import evidence as _evidence_model  # noqa: F401
from app.models import research as _research_model  # noqa: F401
from app.models import source as _source_model  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Phase 2からテーブル管理はAlembicのmigrationに一本化した
    # (`alembic upgrade head`)。ただし使い捨てのSQLite(pytestの一時DB)は
    # 毎回migrationを流すほどの価値がないため、その場合だけ従来通り
    # create_all()で即席にテーブルを作る。
    # 理由の詳細はREADMEの「Migrationについて」を参照。
    if settings.database_url.startswith("sqlite"):
        Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="TechCompare AI API", lifespan=lifespan)

# Nextjsのdevサーバー(localhost:3000)からのAPI呼び出しを許可する。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(research_router)
app.include_router(evidence_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
