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

    # Cloudflare Pages (dynamic subdomain)
    CLOUDFLARE_PAGES_DOMAIN: Optional[str] = Field(
        None,
        env="CLOUDFLARE_PAGES_DOMAIN"
    )

    # AinaReports + AinaProtocol frontends
    AINA_REPORTS_DOMAINS: List[str] = [
        "https://ainareports.com",
        "https://www.ainareports.com",
        "https://ainaprotocol.com",
        "https://www.ainaprotocol.com",
    ]

    # -------------------------------------------------
    # JWT / Auth
    # -------------------------------------------------
    JWT_SECRET_KEY: str = Field(..., env="JWT_SECRET_KEY")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 1 day token expiry

    # -------------------------------------------------
    # Supabase (Primary DB)
    # -------------------------------------------------
    SUPABASE_URL: Optional[str] = Field(None, env="SUPABASE_URL")
    SUPABASE_API_KEY: Optional[str] = Field(None, env="SUPABASE_API_KEY")

    # -------------------------------------------------
    # SMTP Email Notifications
    # -------------------------------------------------
    SMTP_HOST: Optional[str] = Field(None, env="SMTP_HOST")
    SMTP_PORT: Optional[int] = Field(None, env="SMTP_PORT")
    SMTP_USER: Optional[str] = Field(None, env="SMTP_USER")
    SMTP_PASS: Optional[str] = Field(None, env="SMTP_PASS")
    SMTP_TO: Optional[str] = Field(None, env="SMTP_TO")

    # -------------------------------------------------
    # Core
    # -------------------------------------------------
    class Config:
        case_sensitive = True
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
