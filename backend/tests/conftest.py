"""pytest共通設定。

Phase 1のテストでは、実際のPostgreSQL(Docker)を起動しなくても
テストが完結するように、DATABASE_URLをテスト専用のSQLiteファイルに
差し替えている。

app.db.session はモジュール読み込み時に settings.database_url を使って
engineを作るため、この差し替えは "app" 配下を最初にimportするより
前に行う必要がある。
"""

import json
import os
import tempfile

_db_fd, _db_path = tempfile.mkstemp(suffix=".db")
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"

import pytest  # noqa: E402
import requests  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture()
def client():
    """アプリのlifespan(テーブル作成)を通したTestClientを返す。"""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def _disable_gemini_pacing_by_default(monkeypatch):
    """Phase 4.1で追加したGemini呼び出し間のペース管理(pace_gemini_request）は、
    テストで実時間のsleepを起こさないよう既定で無効化(間隔0)しておく。

    pace_gemini_request()自体の挙動を検証したいテストは、そのテスト内で
    `settings.gemini_min_request_interval_seconds` を明示的に上書きすればよい
    (monkeypatchは後勝ちで、どちらもテスト終了時に元に戻る)。
    """
    monkeypatch.setattr(
        "app.services.llm_client.settings.gemini_min_request_interval_seconds", 0
    )


def make_genai_api_error(error_cls, status_code, message, status, details=None):
    """テスト用に genai_errors.ClientError/ServerError を組み立てるhelper。

    google-genai>=1.2 の APIError.__init__ は、第2引数の response が
    requests.Response でない場合 response.body_segments を参照する実装に
    なっており、生のdictを渡す旧来のやり方は AttributeError になる。
    ここではJSON本文を積んだ本物の requests.Response を組み立てて渡すことで、
    SDKの公開contract(requests.Response)の範囲内でエラーを再現する。

    details: Google実APIの `error.details` 配列を模した値(省略可)。
    Phase 5G: Error diagnostics のテスト用に、ErrorInfo/QuotaFailure相当の
    辞書を渡せるようにする(既存呼び出し側との後方互換のため省略可能)。
    """
    error_body: dict = {"message": message, "status": status}
    if details is not None:
        error_body["details"] = details
    response = requests.Response()
    response.status_code = status_code
    response._content = json.dumps({"error": error_body}).encode("utf-8")
    return error_cls(status_code, response)
