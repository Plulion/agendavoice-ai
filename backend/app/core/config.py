from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, model_validator

class Settings(BaseSettings):
    app_name: str = "AgendaVoice AI"
    app_env: str = "local"
    database_url: str = "postgresql+psycopg://agendavoice_app:local_app_change_me@db:5432/agendavoice"
    redis_url: str = "redis://redis:6379/0"
    jwt_secret: str = Field(default="CHANGE_ME_local_only_32_chars_minimum", min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = Field(default=30, gt=0, le=1440)
    refresh_token_days: int = Field(default=14, gt=0, le=90)
    cors_origins: str = "http://localhost:5173"
    rate_limit_enabled: bool = True
    # Only enable behind a trusted reverse proxy that overwrites X-Forwarded-For.
    trust_proxy_headers: bool = False
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_phone_number: str = ""
    gemini_api_key: str = ""
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    @model_validator(mode="after")
    def reject_placeholder_production_secret(self):
        if self.app_env.lower() in {"prod", "production"} and self.jwt_secret.startswith("CHANGE_ME"):
            raise ValueError("JWT_SECRET must be replaced before running in production")
        return self

    @property
    def cors_origin_list(self): return [v.strip() for v in self.cors_origins.split(",") if v.strip()]

settings = Settings()
