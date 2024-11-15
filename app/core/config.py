# app/core/config.py
import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Configuration class for environment variables and service settings.
    """
    service_name: str = "authService"
    rabbitmq_url: str = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
    database_url: str = os.getenv("DATABASE_URL", "postgresql+asyncpg://testuser:testpassword@localhost:5432/main_db")
    test_database_url: str = os.getenv("TEST_DATABASE_URL",
                                       "postgresql+asyncpg://testuser:testpassword@localhost:5432/test_db")

    # MongoDB settings
    mongodb_host: str = os.getenv("MONGODB_HOST", "localhost")
    mongodb_port: int = int(os.getenv("MONGODB_PORT", "27017"))
    mongodb_username: str = os.getenv("MONGODB_USERNAME", "appUser")
    mongodb_password: str = os.getenv("MONGODB_PASSWORD", "password123")
    mongodb_database: str = os.getenv("MONGODB_DATABASE", "main_db")
    mongodb_auth_source: str = os.getenv("MONGODB_AUTH_SOURCE", "main_db")  # Added auth source

    # Construct MongoDB URI with auth source
    @property
    def mongodb_uri(self) -> str:
        return f"mongodb://{self.mongodb_username}:{self.mongodb_password}@{self.mongodb_host}:{self.mongodb_port}/{self.mongodb_database}?authSource={self.mongodb_auth_source}"

    secret_key: str = "your-secret-key-here"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    model_config = SettingsConfigDict(env_file=".env")