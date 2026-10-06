from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_url: str = "sqlite:///./quality.db"
    redis_url: str = "redis://redis:6379/0"
    storage_path: str = "/data"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-mini"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()

