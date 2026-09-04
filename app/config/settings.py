from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from pathlib import Path

class Settings(BaseSettings):
    DATABASE_URL: str = Field(default="postgresql://postgres:postgres@localhost:5433/virtual_league")
    
    MATCHES_URL: str = Field(default="https://bet261.mg/virtual/category/instant-league/8065/matches")
    RESULTS_URL: str = Field(default="https://bet261.mg/virtual/category/instant-league/8065/results")
    RANKING_URL: str = Field(default="https://bet261.mg/virtual/category/instant-league/8065/ranking")
    
    LEAGUE_ID: int = Field(default=8065)
    LEAGUE_NAME: str = Field(default="World Cup")
    
    POLL_INTERVAL_SECONDS: int = Field(default=10)
    REQUEST_TIMEOUT_SECONDS: int = Field(default=20)
    MAX_RETRIES: int = Field(default=3)
    RAW_DATA_DIR: Path = Field(default=Path("./data/raw"))
    
    LOG_LEVEL: str = Field(default="INFO")
    BROWSER_HEADLESS: bool = Field(default=True)
    
    # Event final sync settings (for resolving last-goal race condition)
    EVENT_FINAL_SYNC_MAX_ATTEMPTS: int = Field(default=5)
    EVENT_FINAL_SYNC_DELAY_MS: int = Field(default=1000)

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
