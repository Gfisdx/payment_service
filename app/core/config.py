import os

from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = os.getenv("ENV_FILE", ".env")

class Settings(BaseSettings):
    app_name: str = "payment-service"
    debug: bool = False

    database_url: str

    rabbitmq_url: str

    api_key: str

    webhook_timeout: float = 5.0
    
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
