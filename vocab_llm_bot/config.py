from google_auth_oauthlib.flow import Flow
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

SETTINGS_PATH = Path(__file__).parent.parent / '.settings'
SETTINGS_PATH.mkdir(exist_ok=True)

DATABASE_URL = SETTINGS_PATH / "app.db"


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

    openai_api_key: str
    telegram_bot_token: str


class GoogleServiceAccount(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore', env_prefix='GOOGLE_SERVICE_ACCOUNT_')
    path: str = str(
        SETTINGS_PATH / 'service_account.json'
    )

    def get_service_account_info(self) -> dict:
        import json
        with open(self.path, 'r') as f:
            return json.load(f)
    
    def get_client_email(self) -> str:
        info = self.get_service_account_info()
        return info['client_email']
