from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Application
    PROJECT_NAME: str = "Inversity API"
    ENVIRONMENT: str = "development"
    PORT: int = 8888

    # Log
    LOG_LEVEL: str = "debug"
    LOG_PRETTY_JSON: bool = True

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost:5432/dbname"

    # Cache
    REDIS_URL: str = "redis://localhost:6379/0"

    # Authentication
    AUTH_SECRET_KEY: str = "supersecretkey"
    AUTH_ALGORITHM: str = "HS256"
    AUTH_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    AUTH_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    class Config:
        env_file = ".env"


settings = Settings()
