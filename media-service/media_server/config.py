"""
Configuration settings for Media Service
"""
from pydantic_settings import BaseSettings
from typing import Literal


class Settings(BaseSettings):
    """Application settings"""

    # Application
    APP_NAME: str = "Instagram Media Service"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/instagram"
    DB_POOL_SIZE: int = 10

    # S3/MinIO Storage
    STORAGE_TYPE: Literal["s3", "minio"] = "minio"
    S3_BUCKET_NAME: str = "instagram-media"
    S3_ENDPOINT_URL: str = "http://localstack:4566"
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "us-east-1"

    # Media Processing
    MAX_FILE_SIZE_MB: int = 100
    ALLOWED_IMAGE_EXTENSIONS: list = [".jpg", ".jpeg", ".png", ".gif", ".webp"]
    ALLOWED_VIDEO_EXTENSIONS: list = [".mp4", ".mov", ".avi", ".mkv"]

    # Image sizes for Instagram-like service
    IMAGE_SIZES: dict = {
        "thumbnail": (150, 150),
        "small": (320, 320),
        "medium": (640, 640),
        "large": (1080, 1080)
    }

    THUMBNAIL_QUALITY: int = 85
    IMAGE_QUALITY: int = 90

    # Auth Service
    AUTH_SERVICE_URL: str = "http://localhost:8001"

    # CORS
    CORS_ORIGINS: list = ["*"]
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: list = ["*"]
    CORS_ALLOW_HEADERS: list = ["*"]

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
