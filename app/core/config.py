import os
from typing import Optional, Dict, Any, Tuple
from pydantic_settings import BaseSettings, SettingsConfigDict
from app.log.logging import logger


class Settings(BaseSettings):
    """
    Configuration class for environment variables and service settings.
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"  # Ignore extra fields not defined in the class
    )
    # Service settings
    #service_name: str = os.getenv("SERVICE_NAME", "authService")
    #environment: str = os.getenv("ENVIRONMENT", "development")
    debug: bool = os.getenv("DEBUG", "True").lower() == "true"

    # Logging settings
    # log_level: str = os.getenv("LOG_LEVEL", "DEBUG")
    # syslog_host: str = os.getenv("SYSLOG_HOST", "172.17.0.1")
    # syslog_port: int = int(os.getenv("SYSLOG_PORT", "5141"))
    # json_logs: bool = os.getenv("JSON_LOGS", "True").lower() == "true"
    # log_retention: str = os.getenv("LOG_RETENTION", "7 days")
    # enable_logstash: bool = os.getenv("ENABLE_LOGSTASH", "True").lower() == "true"

    # Database settings
    database_url: str = os.getenv("DATABASE_URL", "postgresql+asyncpg://testuser:testpassword@172.17.0.1:5432/main_db")
    test_database_url: str = os.getenv("TEST_DATABASE_URL", "postgresql+asyncpg://testuser:testpassword@172.17.0.1:5432/test_db")

    # Authentication settings
    secret_key: str = os.getenv("SECRET_KEY", "your-secret-key-here")
    algorithm: str = os.getenv("ALGORITHM", "HS256")
    access_token_expire_minutes: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

    # Email settings - Legacy SMTP settings (kept for backward compatibility)
    MAIL_USERNAME: Optional[str] = os.getenv("MAIL_USERNAME")
    MAIL_PASSWORD: Optional[str] = os.getenv("MAIL_PASSWORD")
    MAIL_FROM: Optional[str] = os.getenv("MAIL_FROM", "noreply@example.com")
    MAIL_PORT: int = int(os.getenv("MAIL_PORT", "587"))
    MAIL_SERVER: Optional[str] = os.getenv("MAIL_SERVER")
    MAIL_SSL_TLS: bool = os.getenv("MAIL_SSL_TLS", "True").lower() == "true"
    MAIL_STARTTLS: bool = os.getenv("MAIL_STARTTLS", "True").lower() == "true"

    # SendGrid via Azure settings
    SENDGRID_API_KEY: str = os.getenv("SENDGRID_API_KEY", "")
    SENDGRID_HOST: str = os.getenv("SENDGRID_HOST", "https://api.sendgrid.com")
    AZURE_DOMAIN: str = os.getenv("AZURE_DOMAIN", "em8606.laborolabs.com")
    EMAIL_FROM_NAME: str = os.getenv("EMAIL_FROM_NAME", "Auth Service")
    EMAIL_FROM_ADDRESS: str = os.getenv("EMAIL_FROM_ADDRESS", f"noreply@{os.getenv('AZURE_DOMAIN', 'em8606.laborolabs.com')}")

    # Frontend URL for reset link
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:3000")
    
    # Stripe API settings
    STRIPE_SECRET_KEY: str = os.getenv("STRIPE_SECRET_KEY", "")
    STRIPE_WEBHOOK_SECRET: str = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    STRIPE_API_VERSION: str = os.getenv("STRIPE_API_VERSION", "2023-10-16")
    
settings = Settings()


def validate_email_config() -> Tuple[bool, Dict[str, Any]]:
    """
    Validate email configuration and log warnings for missing or invalid settings.
    
    Returns:
        Tuple[bool, Dict[str, Any]]:
            - Boolean indicating if configuration is valid
            - Dictionary with validation details
    """
    valid = True
    issues = []
    warnings = []
    
    # Check SendGrid API key
    if not settings.SENDGRID_API_KEY:
        issue = "SendGrid API key not configured (SENDGRID_API_KEY)"
        logger.error(
            issue,
            event_type="config_error",
            setting="SENDGRID_API_KEY"
        )
        issues.append(issue)
        valid = False
    
    # Check FROM email address
    if not settings.EMAIL_FROM_ADDRESS:
        issue = "Email FROM address not configured (EMAIL_FROM_ADDRESS)"
        logger.error(
            issue,
            event_type="config_error",
            setting="EMAIL_FROM_ADDRESS"
        )
        issues.append(issue)
        valid = False
    
    # Check FROM name (warning only)
    if not settings.EMAIL_FROM_NAME:
        warning = "Email FROM name not configured (EMAIL_FROM_NAME)"
        logger.warning(
            warning,
            event_type="config_warning",
            setting="EMAIL_FROM_NAME"
        )
        warnings.append(warning)
    
    # Check Frontend URL (warning only)
    if not settings.FRONTEND_URL:
        warning = "Frontend URL not configured (FRONTEND_URL)"
        logger.warning(
            warning,
            event_type="config_warning",
            setting="FRONTEND_URL"
        )
        warnings.append(warning)
    
    # Check Azure domain (warning only)
    if not settings.AZURE_DOMAIN:
        warning = "Azure domain not configured (AZURE_DOMAIN)"
        logger.warning(
            warning,
            event_type="config_warning",
            setting="AZURE_DOMAIN"
        )
        warnings.append(warning)
    
    return valid, {
        "valid": valid,
        "issues": issues,
        "warnings": warnings
    }


def validate_stripe_config() -> Tuple[bool, Dict[str, Any]]:
    """
    Validate Stripe configuration and log warnings for missing or invalid settings.
    
    Returns:
        Tuple[bool, Dict[str, Any]]:
            - Boolean indicating if configuration is valid
            - Dictionary with validation details
    """
    valid = True
    issues = []
    warnings = []
    
    # Check Stripe API key
    if not settings.STRIPE_SECRET_KEY:
        issue = "Stripe API key not configured (STRIPE_SECRET_KEY)"
        logger.error(
            issue,
            event_type="config_error",
            setting="STRIPE_SECRET_KEY"
        )
        issues.append(issue)
        valid = False
    
    # Check Stripe webhook secret (warning only)
    if not settings.STRIPE_WEBHOOK_SECRET:
        warning = "Stripe webhook secret not configured (STRIPE_WEBHOOK_SECRET)"
        logger.warning(
            warning,
            event_type="config_warning",
            setting="STRIPE_WEBHOOK_SECRET"
        )
        warnings.append(warning)
    
    return valid, {
        "valid": valid,
        "issues": issues,
        "warnings": warnings
    }
