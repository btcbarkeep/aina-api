# core/config.py
from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import AnyHttpUrl, Field


class Settings(BaseSettings):
    # -------------------------------------------------
    # General
    # -------------------------------------------------
    PROJECT_NAME: str = "Aina Protocol API"
    ENV: str = "development"

    # API versioning
    API_V1_PREFIX: str = "/api/v1"

    # -------------------------------------------------
    # CORS
    # -------------------------------------------------
    BACKEND_CORS_ORIGINS: List[AnyHttpUrl] = []

    # -------------------------------------------------
    # JWT / Auth
    # -------------------------------------------------
    JWT_SECRET_KEY: str = Field(..., env="JWT_SECRET_KEY")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 1 day

    # Admin credentials (current single-admin flow)
    ADMIN_USERNAME: str = Field("admin", env="ADMIN_USERNAME")
    ADMIN_PASSWORD: str = Field("strongpassword", env="ADMIN_PASSWORD")

    # -------------------------------------------------
    # Supabase
    # -------------------------------------------------
    SUPABASE_URL: Optional[AnyHttpUrl] = Field(None, env="SUPABASE_URL")
    SUPABASE_API_KEY: Optional[str] = Field(None, env="SUPABASE_KEY")

    # -------------------------------------------------
    # Class Config
    # -------------------------------------------------
    class Config:
        case_sensitive = True
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
