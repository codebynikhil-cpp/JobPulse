from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    app_origin: str = "http://localhost:3000"
    cookie_secure: bool = False
    trust_forwarded_for: bool = False
    session_hours: int = Field(default=168, ge=1, le=8760)
    auth_failure_limit: int = Field(default=5, ge=1, le=100)
    auth_window_seconds: int = Field(default=900, ge=1, le=86400)

    @property
    def cookie_name(self) -> str:
        return "__Host-jobpulse_session" if self.cookie_secure else "jobpulse_session"


settings = Settings()
