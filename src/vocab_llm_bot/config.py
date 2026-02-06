import logging
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

SETTINGS_PATH = Path(__file__).parent.parent.parent / ".conf"
SETTINGS_PATH.mkdir(exist_ok=True)

DATABASE_URL = SETTINGS_PATH / "app.db"

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    openai_api_key: str | None = None
    gemini_api_key: str | None = None
    telegram_bot_token: str | None = None


GOOGLE_SHEET_SCOPES: list[str] = ["https://www.googleapis.com/auth/spreadsheets"]


class GoogleServiceAccount(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", env_prefix="GOOGLE_SERVICE_ACCOUNT_"
    )
    path: str = str(SETTINGS_PATH / "service_account.json")

    def get_service_account_info(self) -> dict:
        import json

        with open(self.path, "r") as f:
            return json.load(f)

    def get_client_email(self) -> str:
        info = self.get_service_account_info()
        return info["client_email"]

    def get_credentials(self):
        from google.oauth2.service_account import Credentials

        info = self.get_service_account_info()
        creds = Credentials.from_service_account_info(info, scopes=GOOGLE_SHEET_SCOPES)
        return creds
