from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import AnyHttpUrl, Field


class Settings(BaseSettings):
    # -------------------------------------------------
    # General
    # -------------------------------------------------
    PROJECT_NAME: str = "Aina Protocol API"
    ENV: str = "development"

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
    # Supabase (Primary DB & Auth)
    # -------------------------------------------------
    SUPABASE_URL: Optional[str] = Field(None, env="SUPABASE_URL")
    SUPABASE_ANON_KEY: Optional[str] = Field(None, env="SUPABASE_ANON_KEY")
    SUPABASE_SERVICE_ROLE_KEY: Optional[str] = Field(None, env="SUPABASE_SERVICE_ROLE_KEY")
    SUPABASE_JWT_SECRET: Optional[str] = Field(None, env="SUPABASE_JWT_SECRET")

    # -------------------------------------------------
    # SMTP Email Notifications
    # -------------------------------------------------
    SMTP_HOST: Optional[str] = Field(None, env="SMTP_HOST")
    SMTP_PORT: Optional[int] = Field(None, env="SMTP_PORT")
    SMTP_USER: Optional[str] = Field(None, env="SMTP_USER")
    SMTP_PASS: Optional[str] = Field(None, env="SMTP_PASS")
    SMTP_TO: Optional[str] = Field(None, env="SMTP_TO")

    # Admin report destination
    ADMIN_REPORT_EMAIL: Optional[str] = Field(None, env="ADMIN_REPORT_EMAIL")

    # -------------------------------------------------
    # Webhooks / Sync notifications
    # -------------------------------------------------
    SYNC_WEBHOOK_URL: Optional[str] = Field(None, env="SYNC_WEBHOOK_URL")

    # -------------------------------------------------
    # Stripe Payment Processing
    # -------------------------------------------------
    STRIPE_SECRET_KEY: Optional[str] = Field(None, env="STRIPE_SECRET_KEY")
    STRIPE_WEBHOOK_SECRET: Optional[str] = Field(None, env="STRIPE_WEBHOOK_SECRET")
    
    # -------------------------------------------------
    # Subscription Trial Limits
    # -------------------------------------------------
    # Self-service trial limits (users starting their own trials)
    TRIAL_SELF_SERVICE_MAX_DAYS: int = Field(14, env="TRIAL_SELF_SERVICE_MAX_DAYS", description="Maximum trial days users can request themselves (default: 14)")
    TRIAL_SELF_SERVICE_MIN_DAYS: int = Field(1, env="TRIAL_SELF_SERVICE_MIN_DAYS", description="Minimum trial days for self-service (default: 1)")
    
    # Admin trial limits (admins granting trials to users)
    TRIAL_ADMIN_MAX_DAYS: int = Field(180, env="TRIAL_ADMIN_MAX_DAYS", description="Maximum trial days admins can grant (default: 180)")
    TRIAL_ADMIN_MIN_DAYS: int = Field(1, env="TRIAL_ADMIN_MIN_DAYS", description="Minimum trial days for admin grants (default: 1)")

    # -------------------------------------------------
    # Model Config
    # -------------------------------------------------
    class Config:
        case_sensitive = True
        # ❌ Removed env_file=".env"
        # Render will now use REAL environment variables


# Instantiate settings
settings = Settings()

# -------------------------------------------------
# Build CORS list dynamically after loading settings
# -------------------------------------------------
cors_origins = []

# 1) add Cloudflare Pages custom domain
if settings.CLOUDFLARE_PAGES_DOMAIN:
    domain = settings.CLOUDFLARE_PAGES_DOMAIN
    if not domain.startswith("http"):
        domain = f"https://{domain}"
    cors_origins.append(domain.rstrip("/"))

# 2) add AinaReports & AinaProtocol domains
cors_origins.extend([d.rstrip("/") for d in settings.AINA_REPORTS_DOMAINS])

# 3) remove duplicates
settings.BACKEND_CORS_ORIGINS = sorted(list(set(cors_origins)))
