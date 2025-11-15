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
    # Cloudflare + Frontend Domains
    # -------------------------------------------------
    CLOUDFLARE_PAGES_DOMAIN: Optional[str] = Field(
        None,
        env="CLOUDFLARE_PAGES_DOMAIN"
    )

    AINA_REPORTS_DOMAINS: List[str] = [
        "https://ainareports.com",
        "https://www.ainareports.com",
        "https://ainaprotocol.com",
        "https://www.ainaprotocol.com",
    ]

    # -------------------------------------------------
    # CORS (auto-built below)
    # -------------------------------------------------
    BACKEND_CORS_ORIGINS: List[str] = []

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
    # Model Config
    # -------------------------------------------------
    class Config:
        case_sensitive = True
        env_file = ".env"
        env_file_encoding = "utf-8"


# Instantiate settings
settings = Settings()

# -------------------------------------------------
# Build CORS list dynamically after loading settings
# -------------------------------------------------
cors_origins = []

# 1) add Pages domain if set
if settings.CLOUDFLARE_PAGES_DOMAIN:
    domain = settings.CLOUDFLARE_PAGES_DOMAIN
    if not domain.startswith("http"):
        domain = f"https://{domain}"
    cors_origins.append(domain.rstrip("/"))

# 2) add AinaReports + AinaProtocol domains
cors_origins.extend([d.rstrip("/") for d in settings.AINA_REPORTS_DOMAINS])

# 3) dedupe
settings.BACKEND_CORS_ORIGINS = sorted(list(set(cors_origins)))
