from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from pathlib import Path
import secrets

class Settings(BaseSettings):
    database_path: str = "./data/evidencearch.sqlite3"
    storage_path: str = "./data/evidence"
    demo_mode: bool = True
    max_upload_bytes: int = 50 * 1024 * 1024
    jwt_secret: str = Field(default_factory=lambda: secrets.token_urlsafe(48))
    jwt_expire_minutes: int = 60
    cookie_secure: bool = False
    cors_origins: list[str] = ["http://127.0.0.1:5173", "http://localhost:5173"]
    model_config = SettingsConfigDict(env_prefix="EVIDENCEARCH_", env_file=".env", extra="ignore")
    def prepare(self):
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        Path(self.storage_path).mkdir(parents=True, exist_ok=True)
settings = Settings()
