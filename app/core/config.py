import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """
    Configuration class for environment variables and service settings.

    Attributes:
        rabbitmq_url (str): The connection URL for RabbitMQ.
        service_name (str): The name of the service.
        database_url (str): The connection URL for the PostgreSQL database.
    """
    rabbitmq_url: str = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
    service_name: str = "authService"
    database_url: str = os.getenv("DATABASE_URL", "postgresql+asyncpg://user:password@localhost:5432/auth_db")

    model_config = SettingsConfigDict(env_file=".env")
