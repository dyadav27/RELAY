from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(REPO_DIR / ".env", BACKEND_DIR / ".env"), extra="ignore")

    database_url: str = f"sqlite:///{(BACKEND_DIR / 'relay_local.db').as_posix()}"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    gemini_timeout_seconds: float = 45.0
    log_file_path: str = str(BACKEND_DIR / "logs" / "relay.jsonl")
    log_level: str = "INFO"
    frontend_dist: str = str(REPO_DIR / "frontend" / "dist")
    seed_demo_data: bool = False
    max_upload_bytes: int = 5 * 1024 * 1024

    @property
    def sqlalchemy_url(self) -> str:
        url = self.database_url
        # Supabase / Render hand out postgres:// or postgresql:// URLs; use the psycopg 3 driver.
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://"):]
        if url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url[len("postgresql://"):]
        # Hosted databases (Supabase) must be encrypted; libpq's default "prefer" would silently allow plaintext.
        if url.startswith("postgresql+psycopg://") and "sslmode=" not in url and \
                urlsplit(url).hostname not in (None, "localhost", "127.0.0.1", "::1"):
            url += ("&" if "?" in url else "?") + "sslmode=require"
        return url

    @property
    def ai_configured(self) -> bool:
        return bool(self.gemini_api_key and self.gemini_api_key.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
