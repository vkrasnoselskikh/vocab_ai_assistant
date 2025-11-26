from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

SETTINGS_PATH = Path(__file__).parent.parent / '.settings'
SETTINGS_PATH.mkdir(exist_ok=True)


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

    openai_api_key: str
    telegram_bot_token:str
    

class GoogleAuthConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore', prefix='GOOGLE_')

    scopes: list[str] = ['https://www.googleapis.com/auth/drive.file']
    redirect_url: str
 