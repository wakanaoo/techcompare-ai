"""アプリ全体の設定を1箇所に集約するモジュール。

環境変数(または backend/.env)から値を読み込む。
秘密情報(DATABASE_URLに含まれるパスワードや、GEMINI_API_KEY)はコード中に
直接書かず、必ずここ(または環境変数)を経由して取得する。
"""

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# google-genai SDKは GEMINI_API_KEY を「プロセスの環境変数」から直接読むため、
# pydantic-settingsの読み込みとは別に、.envの内容を明示的に
# os.environ へ反映しておく(値そのものはここでは扱わない/表示しない)。
load_dotenv()


class Settings(BaseSettings):
    database_url: str

    # GEMINI_API_KEYのように、Settingsのフィールドとして宣言していない変数が
    # .envに含まれていてもエラーにしない(google-genai SDK自身がos.environから
    # 直接読むため、ここで改めてフィールド化する必要はない)。
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


settings = Settings()
