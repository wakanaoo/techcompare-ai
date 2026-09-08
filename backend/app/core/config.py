"""アプリ全体の設定を1箇所に集約するモジュール。

環境変数(または backend/.env)から値を読み込む。
秘密情報(DATABASE_URLに含まれるパスワードなど)はコード中に直接書かず、
必ずここを経由して環境変数から取得する。
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
