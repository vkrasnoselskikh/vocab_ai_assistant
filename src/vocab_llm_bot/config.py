import base64
import logging
from pathlib import Path
from typing import cast

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

SETTINGS_PATH = Path(__file__).parent.parent.parent / ".conf"
SETTINGS_PATH.mkdir(exist_ok=True)


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    openai_api_key: str | None = None
    gemini_api_key: str | None = None
    telegram_bot_token: str | None = None


class DatabaseConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_dsn: str = Field(default=f"sqlite+aiosqlite://{SETTINGS_PATH}/app.db")


GOOGLE_SHEET_SCOPES: list[str] = ["https://www.googleapis.com/auth/spreadsheets"]


class GoogleServiceAccount(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", env_prefix="GOOGLE_SERVICE_ACCOUNT_"
    )
    path: str = Field(default=str(SETTINGS_PATH / "service_account.json"))
    b64_value: str | None = None

    def get_service_account_info(self) -> dict[str, object]:
        import json

        if self.b64_value:
            b64_value = base64.b64decode(self.b64_value).decode("utf-8")
            return json.loads(b64_value)

        with open(self.path, "r") as f:
            return json.load(f)

    def get_client_email(self) -> str:
        info = self.get_service_account_info()
        return cast(str, info["client_email"])

    def get_credentials(self):
        from google.oauth2.service_account import Credentials

        info = self.get_service_account_info()
        creds = Credentials.from_service_account_info(info, scopes=GOOGLE_SHEET_SCOPES)
        return creds
