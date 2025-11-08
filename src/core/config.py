# src/core/config.py
from typing import List, Optional

from pydantic import BaseSettings, AnyHttpUrl, Field


class Settings(BaseSettings):
    # General
    PROJECT_NAME: str = "Aina Protocol API"
    ENV: str = "development"

    # API versioning
    API_V1_PREFIX: str = "/api/v1"

    # CORS
    BACKEND_CORS_ORIGINS: List[AnyHttpUrl] = []

    # JWT / auth
    JWT_SECRET_KEY: str = Field(..., env="JWT_SECRET_KEY")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 1 day

    # Admin credentials (for your current single-admin flow)
    ADMIN_USERNAME: str = Field("admin", env="ADMIN_USERNAME")
    ADMIN_PASSWORD: str = Field("changeme", env="ADMIN_PASSWORD")

    # Supabase (will wire up later)
    SUPABASE_URL: Optional[AnyHttpUrl] = None
    SUPABASE_API_KEY: Optional[str] = None

    class Config:
        case_sensitive = True
        env_file = ".env"


settings = Settings()
