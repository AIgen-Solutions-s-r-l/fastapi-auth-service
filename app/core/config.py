import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Configuration class for environment variables and service settings.
    """
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

    
settings = Settings()
