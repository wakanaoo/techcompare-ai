"""DB接続(SQLAlchemy Engine/Session)の設定。

Phase 1ではAlembicなどのmigrationツールは導入せず、
アプリ起動時に Base.metadata.create_all() でテーブルを作成する
簡易運用にしている(理由はREADMEの「Migrationについて」を参照)。
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

# SQLiteはデフォルトで「作成したスレッドでしか使えない」制約があり、
# テスト(pytestのTestClient)がこれに引っかかるため、
# sqlite利用時のみ check_same_thread=False を渡す。
# PostgreSQL利用時(本番/開発)には影響しない。
_connect_args = (
    {"check_same_thread": False}
    if settings.database_url.startswith("sqlite")
    else {}
)

engine = create_engine(settings.database_url, connect_args=_connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """全モデルの共通ベースクラス。"""


def get_db():
    """FastAPIのDependsで使うDBセッションのライフサイクル管理。

    リクエストごとにセッションを開き、処理が終わったら必ずcloseする。
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
