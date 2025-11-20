"""
Configuration settings for Newsfeed Service
"""
from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    """Application settings"""

    # Application
    APP_NAME: str = "Instagram Newsfeed Service"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8004

    # Database (PostgreSQL via pgdog)
    DATABASE_URL: str = "postgresql://instagram_user:instagram_password@localhost:6432/instagram"
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10

    # Redis (for caching timeline)
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 1  # Different DB from graph service
    REDIS_PASSWORD: str = ""
    REDIS_ENABLED: bool = True

    # Auth Service Integration
    AUTH_SERVICE_URL: str = "http://localhost:8001"
    JWT_SECRET_KEY: str = "your-secret-key-change-this-in-production"
    JWT_ALGORITHM: str = "HS256"

    # Other Services
    POST_SERVICE_URL: str = "http://localhost:8002"
    GRAPH_SERVICE_URL: str = "http://localhost:8003"
    MEDIA_SERVICE_URL: str = "http://localhost:8000"

    # Kafka
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    KAFKA_ENABLED: bool = True
    KAFKA_CONSUMER_GROUP: str = "newsfeed-service"

    # Kafka Topics - Consume
    KAFKA_TOPIC_POST_CREATED: str = "post.created"
    KAFKA_TOPIC_POST_DELETED: str = "post.deleted"
    KAFKA_TOPIC_FOLLOW_ACCEPTED: str = "follow.accepted"
    KAFKA_TOPIC_UNFOLLOW: str = "follow.removed"

    # Kafka Topics - Produce
    KAFKA_TOPIC_FEED_UPDATED: str = "feed.updated"

    # CORS
    CORS_ORIGINS: List[str] = ["*"]

    # Pagination
    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE: int = 100

    # Feed Settings
    CELEBRITY_FOLLOWER_THRESHOLD: int = 100000  # Fan-out on read for users with > 100k followers
    MAX_FEED_ITEMS_PER_USER: int = 500  # Limit stored feed items per user
    FEED_CACHE_TTL: int = 300  # 5 minutes in seconds

    # Cache TTL (seconds)
    CACHE_TTL_FEED: int = 300  # 5 minutes
    CACHE_TTL_FEED_ITEM: int = 600  # 10 minutes

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
