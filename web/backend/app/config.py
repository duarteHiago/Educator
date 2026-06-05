from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    secret_key: str          # JWT signing — min 32 bytes random
    encryption_key: str      # Fernet key for token encryption (32-byte url-safe base64)
    admin_secret: str        # protects POST /api/admin/users
    litellm_url: str = "http://litellm:4000"
    litellm_master_key: str
    allowed_origin: str = "https://educator.yaatoro.com"
    access_token_expire_minutes: int = 60
    redis_url: str = "redis://redis:6379/0"
    resend_api_key: str = ""          # empty = email notifications disabled
    resend_from_email: str = "educator@educator.yaatoro.com"
    admin_email: str = ""             # receives health check alerts

    model_config = {"env_file": ".env"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
