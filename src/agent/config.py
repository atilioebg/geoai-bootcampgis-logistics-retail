import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    google_api_key: str
    llm_model: str
    database_url: str
    
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
os.environ["GOOGLE_API_KEY"] = settings.google_api_key.split("#")[0].strip()
