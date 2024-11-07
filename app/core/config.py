import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    rabbitmq_url: str = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
    service_name: str = "authService"
    database_url: str = os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/auth_db")

    model_config = SettingsConfigDict(env_file=".env")
