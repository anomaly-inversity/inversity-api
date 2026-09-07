from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "Inversity API"
    ENVIRONMENT: str = "development"
    LOG_PRETTY_JSON: bool = True
    DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost:5432/dbname"
    REDIS_URL: str = "redis://localhost:6379/0"

    class Config:
        env_file = ".env"

settings = Settings()
