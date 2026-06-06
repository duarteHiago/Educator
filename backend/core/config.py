from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Portal UNIC — obrigatório no .exe, opcional no worker (usa UserRunContext)
    portal_url: str = "https://alunodigital.unic.br/pda_unic"
    auth_url: str = "https://login.unic.br/"
    portal_username: str = ""
    portal_password: str = ""

    # Browser
    browser_headless: bool = False
    browser_slow_mo: int = 80
    browser_timeout: int = 30_000

    # Session
    session_file_path: Path = Path("./logs/session.json")

    # LLM — uso local direto
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    llm_model_primary: str = "gpt-4o-mini"
    llm_model_fallback: str = "gpt-4o"
    llm_confidence_threshold: float = 0.75

    # LLM — proxy VPS (distribuição .exe); quando preenchido, tem prioridade
    proxy_url: str = ""
    proxy_token: str = ""

    # Evolution engine
    perf_window_size: int = 3
    perf_accuracy_threshold: float = 0.70
    perf_history_file: Path = Path("./logs/performance_history.json")
    perf_active_config_file: Path = Path("./logs/active_model_config.json")

    # Logs
    log_level: str = "DEBUG"
    log_file: Path = Path("./logs/educator.jsonl")


settings = Settings()  # type: ignore[call-arg]
