"""アプリ全体の設定を1箇所に集約するモジュール。

環境変数(または backend/.env)から値を読み込む。
秘密情報(DATABASE_URLに含まれるパスワードや、GEMINI_API_KEY)はコード中に
直接書かず、必ずここ(または環境変数)を経由して取得する。
"""

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# TavilyClient()は TAVILY_API_KEY を「プロセスの環境変数」から直接読むため、
# pydantic-settingsの読み込みとは別に、.envの内容を明示的に
# os.environ へ反映しておく(値そのものはここでは扱わない/表示しない)。
load_dotenv()


class Settings(BaseSettings):
    database_url: str

    # google-genai SDKがAPIキーを自動探索する際に見る環境変数名はSDKの
    # バージョンによって変わりうる(例: 1.2系ではGOOGLE_API_KEYのみを見て、
    # GEMINI_API_KEYは見ない)。このSDK側の挙動に依存しないよう、
    # GEMINI_API_KEYはここでSettingsのフィールドとして明示的に読み込み、
    # genai.Client(api_key=...)へ明示的に渡す(app/services/llm_client.py参照)。
    gemini_api_key: str

    # --- Gemini APIのrate-limit resilience(Phase 4.1)---
    # 15ケース連続実行時に429(Too Many Requests)が多発した実測(Full
    # Evaluation Run #1)を受けて追加。ハードコードせず、Settings/envで
    # 調整可能にする(app/services/llm_client.py参照)。
    #
    # comparison生成・LLM Judge双方のGemini呼び出しに共通で適用する、
    # 連続リクエスト間の最小間隔(秒)。0にすると間隔を空けない(旧挙動)。
    gemini_min_request_interval_seconds: float = 4.0
    # 429/503retry時の指数バックオフの基準値(秒)。実際の待機は
    # base * 2^attempt + jitter(Retry-Afterヘッダがあればそちらを優先)。
    gemini_retry_backoff_base_seconds: float = 1.0
    # 指数バックオフに加えるjitterの最大値(秒)。0〜この値の一様乱数を加算する。
    gemini_retry_jitter_max_seconds: float = 0.5

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


settings = Settings()
