from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    app_origin: str = "http://localhost:3000"
    cookie_secure: bool = False
    trust_forwarded_for: bool = False
    session_hours: int = Field(default=168, ge=1, le=8760)
    auth_failure_limit: int = Field(default=5, ge=1, le=100)
    auth_window_seconds: int = Field(default=900, ge=1, le=86400)
    monitor_tick_seconds: float = Field(default=10, gt=0, le=3600)
    monitor_source_timeout_seconds: float = Field(default=90, gt=0, le=3600)
    monitor_source_batch_size: int = Field(default=100, ge=1, le=1000)
    monitor_profile_batch_size: int = Field(default=100, ge=1, le=1000)
    monitor_job_batch_size: int = Field(default=100, ge=1, le=1000)
    monitor_anomaly_drop_fraction: float = Field(default=0.5, gt=0, le=1)
    monitor_pause_after_failures: int = Field(default=5, ge=1, le=100)
    browser_provider: Literal["local", "browserbase"] = "local"
    browser_max_sessions: int = Field(default=1, ge=1, le=4)
    browserbase_api_key: SecretStr = SecretStr("")
    browserbase_project_id: str = ""

    @property
    def cookie_name(self) -> str:
        return "__Host-jobpulse_session" if self.cookie_secure else "jobpulse_session"


settings = Settings()
