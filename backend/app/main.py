"""FastAPIアプリのエントリーポイント。"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.research import router as research_router
from app.db.session import Base, engine

# モデルをBase.metadata に登録するためimportしておく(直接は使わない)。
from app.models import research as _research_model  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Phase 1: Alembicは導入せず、起動時にcreate_all()でテーブルを作る簡易運用。
    # (理由はbackend/README.mdの「Migrationについて」を参照)
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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
