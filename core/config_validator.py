# core/config_validator.py

from typing import List, Optional
from core.config import settings
from core.logging_config import logger


def validate_required_config() -> List[str]:
    """
    Validate that all required environment variables are set.
    Returns list of missing required variables.
    """
    missing = []
    
    # Required for core functionality
    if not settings.SUPABASE_URL:
        missing.append("SUPABASE_URL")
    if not settings.SUPABASE_SERVICE_ROLE_KEY:
        missing.append("SUPABASE_SERVICE_ROLE_KEY")
    
    return missing


def validate_optional_config() -> List[str]:
    """
    Validate optional but recommended configuration.
    Returns list of missing optional variables (warnings only).
    """
    warnings = []
    
    # Optional but recommended
    if not settings.SUPABASE_ANON_KEY:
        warnings.append("SUPABASE_ANON_KEY (optional but recommended)")
    
    return warnings


def validate_config_on_startup():
    """
    Validate configuration on application startup.
    Raises RuntimeError if critical config is missing.
    Logs warnings for optional config.
    """
    missing_required = validate_required_config()
    missing_optional = validate_optional_config()
    
    if missing_required:
        error_msg = f"Missing required environment variables: {', '.join(missing_required)}"
        logger.error(error_msg)
        raise RuntimeError(error_msg)
    
    if missing_optional:
        for warning in missing_optional:
            logger.warning(f"Optional configuration missing: {warning}")
    
    logger.info("Configuration validation passed")

