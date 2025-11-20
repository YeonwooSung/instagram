"""
Configuration settings for Graph Service
"""
from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    """Application settings"""

    # Application
    APP_NAME: str = "Instagram Graph Service"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8003

    # Database (PostgreSQL via pgdog)
    DATABASE_URL: str = "postgresql://instagram_user:instagram_password@localhost:6432/instagram"
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10

    # Redis (for caching)
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str = ""
    REDIS_ENABLED: bool = True

    # Auth Service Integration
    AUTH_SERVICE_URL: str = "http://localhost:8001"
    JWT_SECRET_KEY: str = "your-secret-key-change-this-in-production"
    JWT_ALGORITHM: str = "HS256"

    # Kafka
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    KAFKA_ENABLED: bool = True

    # CORS
    CORS_ORIGINS: List[str] = ["*"]

    # Pagination
    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE: int = 100

    # Follow Settings
    MAX_FOLLOWING_LIMIT: int = 7500  # Instagram-like limit
    FOLLOW_REQUEST_EXPIRY_DAYS: int = 30

    # Cache TTL (seconds)
    CACHE_TTL_FOLLOWERS: int = 300  # 5 minutes
    CACHE_TTL_FOLLOWING: int = 300  # 5 minutes
    CACHE_TTL_RELATIONSHIP: int = 600  # 10 minutes
    CACHE_TTL_STATS: int = 60  # 1 minute

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
