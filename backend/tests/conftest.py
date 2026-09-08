"""pytest共通設定。

Phase 1のテストでは、実際のPostgreSQL(Docker)を起動しなくても
テストが完結するように、DATABASE_URLをテスト専用のSQLiteファイルに
差し替えている。

app.db.session はモジュール読み込み時に settings.database_url を使って
engineを作るため、この差し替えは "app" 配下を最初にimportするより
前に行う必要がある。
"""

import os
import tempfile

_db_fd, _db_path = tempfile.mkstemp(suffix=".db")
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture()
def client():
    """アプリのlifespan(テーブル作成)を通したTestClientを返す。"""
    with TestClient(app) as test_client:
        yield test_client
