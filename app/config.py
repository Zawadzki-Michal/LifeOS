from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://lifeos:changeme@localhost:5432/lifeos"
    redis_url: str = "redis://localhost:6379/0"

    telegram_bot_token: str = ""
    telegram_allowed_user_id: int | None = None

    ollama_base_url: str = "http://host.docker.internal:11434"
    ollama_model: str = "qwen3.6:35b-a3b"

    openrouter_api_key: str = ""
    openrouter_model: str = "anthropic/claude-sonnet-5"
    openrouter_vision_model: str = "google/gemini-2.5-flash"

    google_maps_api_key: str = ""

    google_calendar_client_id: str = ""
    google_calendar_client_secret: str = ""
    google_calendar_refresh_token: str = ""

    health_sync_token: str = ""

    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    google_oauth_redirect_uri: str = ""
    webapp_allowed_emails: str = ""
    webapp_secret_key: str = ""

    @field_validator("telegram_allowed_user_id", mode="before")
    @classmethod
    def _blank_to_none(cls, v):
        if v == "" or v is None:
            return None
        return v


settings = Settings()
