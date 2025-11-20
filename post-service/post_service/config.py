"""
Configuration settings for Post Service
"""
from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    """Application settings"""

    # Application
    APP_NAME: str = "Instagram Post Service"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # MongoDB
    MONGODB_URL: str = "mongodb://localhost:27017"
    MONGODB_DATABASE: str = "instagram_posts"
    MONGODB_COLLECTION: str = "posts"

    # Kafka
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    KAFKA_TOPIC_POST_CREATED: str = "post.created"
    KAFKA_TOPIC_POST_UPDATED: str = "post.updated"
    KAFKA_TOPIC_POST_DELETED: str = "post.deleted"
    KAFKA_TOPIC_POST_LIKED: str = "post.liked"
    KAFKA_TOPIC_POST_COMMENTED: str = "post.commented"

    # Auth Service
    AUTH_SERVICE_URL: str = "http://localhost:8001"

    # Media Service
    MEDIA_SERVICE_URL: str = "http://localhost:8000"

    # Pagination
    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE: int = 100

    # CORS
    CORS_ORIGINS: List[str] = ["*"]
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: List[str] = ["*"]
    CORS_ALLOW_HEADERS: List[str] = ["*"]

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
