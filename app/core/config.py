import os
from typing import Optional, Dict, Any, Tuple, List
from pydantic_settings import BaseSettings, SettingsConfigDict
from app.log.logging import logger


def parse_cors_origins(origins_str: str) -> List[str]:
    """Parse comma-separated CORS origins string into a list."""
    if not origins_str:
        return []
    return [origin.strip() for origin in origins_str.split(",") if origin.strip()]


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
    database_url: str = os.getenv("DATABASE_URL", "")
    test_database_url: str = os.getenv("TEST_DATABASE_URL", "")

    # Authentication settings
    secret_key: str = os.getenv("SECRET_KEY", "your-secret-key-here")
    algorithm: str = os.getenv("ALGORITHM", "HS256")
    access_token_expire_minutes: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

    # Email settings (SendGrid via Azure)
    SENDGRID_API_KEY: str = os.getenv("SENDGRID_API_KEY", "")
    SENDGRID_HOST: str = os.getenv("SENDGRID_HOST", "https://api.sendgrid.com")
    AZURE_DOMAIN: str = os.getenv("AZURE_DOMAIN", "example.com")
    EMAIL_FROM_NAME: str = os.getenv("EMAIL_FROM_NAME", "Auth Service")
    EMAIL_FROM_ADDRESS: str = os.getenv("EMAIL_FROM_ADDRESS", f"noreply@{os.getenv('AZURE_DOMAIN', 'example.com')}")

    # Frontend URL for reset link
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:3000")

    # Whitelabel settings
    COMPANY_NAME: str = os.getenv("COMPANY_NAME", "Your Company")
    COMPANY_LEGAL_NAME: str = os.getenv("COMPANY_LEGAL_NAME", "Your Company Inc.")
    COMPANY_ADDRESS: str = os.getenv("COMPANY_ADDRESS", "123 Main Street, City, Country")
    COMPANY_VAT: str = os.getenv("COMPANY_VAT", "")
    SUPPORT_EMAIL: str = os.getenv("SUPPORT_EMAIL", "support@example.com")
    
    # Stripe settings
    STRIPE_SECRET_KEY: str = os.getenv("STRIPE_SECRET_KEY", "")
    STRIPE_WEBHOOK_SECRET: str = os.getenv("STRIPE_WEBHOOK_SECRET", "") # Secret for verifying webhook signatures
    STRIPE_API_VERSION: str = os.getenv("STRIPE_API_VERSION", "2024-06-20")
    STRIPE_FREE_TRIAL_PRICE_ID: str = os.getenv("STRIPE_FREE_TRIAL_PRICE_ID", "price_free_trial")
    FREE_TRIAL_DAYS: int = int(os.getenv("FREE_TRIAL_DAYS", "7"))
    FREE_TRIAL_CREDITS: int = int(os.getenv("FREE_TRIAL_CREDITS", "10"))
    
    # Google OAuth settings
    GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
    GOOGLE_REDIRECT_URI: str = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:3000/api/auth/google-callback")
    OAUTH_SCOPES: str = os.getenv("OAUTH_SCOPES", "openid email profile")
    
    # Service-to-service authentication
    INTERNAL_API_KEY: str = os.getenv("INTERNAL_API_KEY", "")

    # CORS settings
    CORS_ORIGINS: str = os.getenv("CORS_ORIGINS", "http://localhost:3000")
    CORS_ALLOW_CREDENTIALS: bool = os.getenv("CORS_ALLOW_CREDENTIALS", "true").lower() == "true"
    CORS_ALLOW_METHODS: str = os.getenv("CORS_ALLOW_METHODS", "GET,POST,PUT,DELETE,OPTIONS,PATCH")
    CORS_ALLOW_HEADERS: str = os.getenv("CORS_ALLOW_HEADERS", "Authorization,Content-Type,X-API-Key")
    CORS_MAX_AGE: int = int(os.getenv("CORS_MAX_AGE", "600"))

    # Rate limiting settings
    RATE_LIMIT_ENABLED: bool = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
    RATE_LIMIT_DEFAULT: str = os.getenv("RATE_LIMIT_DEFAULT", "100/minute")
    RATE_LIMIT_AUTH: str = os.getenv("RATE_LIMIT_AUTH", "10/minute")
    RATE_LIMIT_STORAGE_URI: str = os.getenv("RATE_LIMIT_STORAGE_URI", "memory://")

    @property
    def cors_origins_list(self) -> List[str]:
        """Get CORS origins as a list."""
        return parse_cors_origins(self.CORS_ORIGINS)

    @property
    def cors_methods_list(self) -> List[str]:
        """Get CORS methods as a list."""
        return parse_cors_origins(self.CORS_ALLOW_METHODS)

    @property
    def cors_headers_list(self) -> List[str]:
        """Get CORS headers as a list."""
        return parse_cors_origins(self.CORS_ALLOW_HEADERS)

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




def validate_oauth_config() -> Tuple[bool, Dict[str, Any]]:
    """
    Validate OAuth configuration and log warnings for missing or invalid settings.
    
    Returns:
        Tuple[bool, Dict[str, Any]]:
            - Boolean indicating if configuration is valid
            - Dictionary with validation details
    """
    valid = True
    issues = []
    warnings = []
    
    # Check Google Client ID
    if not settings.GOOGLE_CLIENT_ID:
        issue = "Google Client ID not configured (GOOGLE_CLIENT_ID)"
        logger.error(
            issue,
            event_type="config_error",
            setting="GOOGLE_CLIENT_ID"
        )
        issues.append(issue)
        valid = False
    
    # Check Google Client Secret
    if not settings.GOOGLE_CLIENT_SECRET:
        issue = "Google Client Secret not configured (GOOGLE_CLIENT_SECRET)"
        logger.error(
            issue,
            event_type="config_error",
            setting="GOOGLE_CLIENT_SECRET"
        )
        issues.append(issue)
        valid = False
    
    # Check Google Redirect URI (warning only)
    if not settings.GOOGLE_REDIRECT_URI:
        warning = "Google Redirect URI not configured (GOOGLE_REDIRECT_URI)"
        logger.warning(
            warning,
            event_type="config_warning",
            setting="GOOGLE_REDIRECT_URI"
        )
        warnings.append(warning)
    
    return valid, {
        "valid": valid,
        "issues": issues,
        "warnings": warnings
    }


def validate_internal_api_key() -> Tuple[bool, Dict[str, Any]]:
    """
    Validate internal service API key configuration.
    
    Returns:
        Tuple[bool, Dict[str, Any]]:
            - Boolean indicating if configuration is valid
            - Dictionary with validation details
    """
    valid = True
    issues = []
    warnings = []
    
    # Check internal API key
    if not settings.INTERNAL_API_KEY:
        issue = "Internal API key not configured (INTERNAL_API_KEY)"
        logger.error(
            issue,
            event_type="config_error",
            setting="INTERNAL_API_KEY"
        )
        issues.append(issue)
        valid = False
    elif len(settings.INTERNAL_API_KEY) < 32:
        warning = "Internal API key may be too short for security (INTERNAL_API_KEY)"
        logger.warning(
            warning,
            event_type="config_warning",
            setting="INTERNAL_API_KEY"
        )
        warnings.append(warning)
    
    return valid, {
        "valid": valid,
        "issues": issues,
        "warnings": warnings
    }
