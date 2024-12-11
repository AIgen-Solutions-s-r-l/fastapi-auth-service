import os
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Configuration class for environment variables and service settings.
    """
    # Service settings
    service_name: str = "authService"
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = True

    # Logging settings
    log_level: str = "DEBUG"
    syslog_host: str = "172.17.0.1"
    syslog_port: int = 5141
    json_logs: bool = True
    log_retention: str = "7 days"

    # RabbitMQ settings
    rabbitmq_url: str = "amqp://guest:guest@172.17.0.1:5672/"

    # Database settings
    database_url: str = "postgresql+asyncpg://testuser:testpassword@172.17.0.1:5432/main_db"
    test_database_url: str = "postgresql+asyncpg://testuser:testpassword@172.17.0.1:5432/test_db"

    # MongoDB settings
    mongodb_host: str = "172.17.0.1"
    mongodb_port: int = 27017
    mongodb_username: str = "appUser"
    mongodb_password: str = "password123"
    mongodb_database: str = "main_db"
    mongodb_auth_source: str = "main_db"

    # Authentication settings
    secret_key: str = "your-secret-key-here"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    # Construct MongoDB URI with auth source
    @property
    def mongodb_uri(self) -> str:
        return f"mongodb://{self.mongodb_username}:{self.mongodb_password}@{self.mongodb_host}:{self.mongodb_port}/{self.mongodb_database}?authSource={self.mongodb_auth_source}"

    # Environment-specific logging configuration
    @property
    def logging_config(self) -> dict:
        """
        Returns logging configuration based on environment.
        """
        base_config = {
            "app_name": self.service_name,
            "log_level": self.log_level,
            "syslog_host": self.syslog_host,
            "syslog_port": self.syslog_port,
            "json_logs": self.json_logs,
        }

        if self.environment == "development":
            base_config.update({
                "json_logs": False,  # Human-readable logs in development
                "log_level": "DEBUG" if self.debug else "INFO"
            })
        elif self.environment == "staging":
            base_config.update({
                "log_level": "DEBUG",
                "json_logs": True
            })
        else:  # production
            base_config.update({
                "log_level": "INFO",
                "json_logs": True
            })

        return base_config

    model_config = SettingsConfigDict(env_file=".env")