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


class GoogleAuthConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore', env_prefix='GOOGLE_')
    app_id: str
    client_secrets: str = str(
        SETTINGS_PATH / 'client_secret_17520064084-tgmob015qji3cn1stsv2ener7grq27ck.apps.googleusercontent.com.json'
    )
    scopes: list[str] = ['https://www.googleapis.com/auth/drive.file']
    authorize_url: str
    redirect_url: str

    def get_flow(self):
        return Flow.from_client_secrets_file(
            self.client_secrets,
            scopes=self.scopes,
            redirect_uri=self.redirect_url,
        )
