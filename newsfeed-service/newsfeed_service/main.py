"""
FastAPI application for Newsfeed Service
"""
from fastapi import FastAPI, Depends, HTTPException, status, Query, Header
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from typing import Optional
import logging

from .config import settings
from .database import db, get_db, Database
from .cache import cache, get_cache, RedisCache
from .service_client import service_client, get_service_client, ServiceClient
from .kafka_producer import kafka_producer, get_kafka_producer, KafkaProducerManager
from .kafka_consumer import kafka_consumer
from .dependencies import get_current_user
from .service import NewsfeedService
from .schemas import (
    User,
    FeedResponse,
    FeedStatsResponse,
    MessageResponse,
    FeedItemResponse,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    logger.info("Starting Newsfeed Service...")

    # Connect to database
    await db.connect()
    logger.info("Database connected")

    # Connect to Redis
    await cache.connect()
    logger.info("Redis cache initialized")

    # Start service client
    await service_client.start()
    logger.info("Service client initialized")

    # Start Kafka producer
    await kafka_producer.start()
    logger.info("Kafka producer started")

    # Start Kafka consumer
    await kafka_consumer.start()
    logger.info("Kafka consumer started")

    logger.info(f"Newsfeed Service started successfully on port {settings.PORT}")

    yield

    # Shutdown
    logger.info("Shutting down Newsfeed Service...")

    # Stop Kafka consumer
    await kafka_consumer.stop()

    # Stop Kafka producer
    await kafka_producer.stop()

    # Stop service client
    await service_client.stop()

    # Disconnect Redis
    await cache.disconnect()

    # Disconnect database
    await db.disconnect()

    logger.info("Newsfeed Service shut down successfully")


# Create FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Instagram Newsfeed Service - Personalized feed with hybrid fan-out strategy",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Helper function to get service instance
def get_newsfeed_service(
    db: Database = Depends(get_db),
    cache: RedisCache = Depends(get_cache),
    service_client: ServiceClient = Depends(get_service_client),
    kafka_producer: KafkaProducerManager = Depends(get_kafka_producer),
) -> NewsfeedService:
    """Get NewsfeedService instance with dependencies"""
    return NewsfeedService(db, cache, service_client, kafka_producer)


# Health check endpoint
@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION
    }


# Feed endpoints
@app.get(
    "/api/v1/feed",
    response_model=FeedResponse,
    tags=["Feed"],
    summary="Get personalized feed",
)
async def get_feed(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(
        settings.DEFAULT_PAGE_SIZE,
        ge=1,
        le=settings.MAX_PAGE_SIZE,
        description="Items per page"
    ),
    current_user: User = Depends(get_current_user),
    service: NewsfeedService = Depends(get_newsfeed_service),
    authorization: Optional[str] = Header(None),
):
    """
    Get personalized feed for current user

    - Uses hybrid fan-out strategy (fan-out on write for regular users, fan-out on read for celebrities)
    - Cached in Redis for fast access
    - Automatically rebuilds stale feeds
    """
    try:
        # Extract token from authorization header
        token = authorization.replace("Bearer ", "") if authorization else None

        feed_items, total, has_more = await service.get_user_feed(
            current_user.id,
            page,
            page_size,
            token
        )

        return FeedResponse(
            items=feed_items,
            total=total,
            page=page,
            page_size=page_size,
            has_more=has_more,
        )

    except Exception as e:
        logger.error(f"Error getting feed for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve feed"
        )


@app.post(
    "/api/v1/feed/refresh",
    response_model=MessageResponse,
    tags=["Feed"],
    summary="Refresh feed",
)
async def refresh_feed(
    current_user: User = Depends(get_current_user),
    service: NewsfeedService = Depends(get_newsfeed_service),
    authorization: Optional[str] = Header(None),
):
    """
    Manually refresh user's feed

    - Clears cache and rebuilds feed from scratch
    - Useful after following new users
    """
    try:
        # Extract token from authorization header
        token = authorization.replace("Bearer ", "") if authorization else None

        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required"
            )

        success = await service.refresh_user_feed(current_user.id, token)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to refresh feed"
            )

        return MessageResponse(message="Feed refreshed successfully")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error refreshing feed for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to refresh feed"
        )


@app.get(
    "/api/v1/feed/stats",
    response_model=FeedStatsResponse,
    tags=["Feed"],
    summary="Get feed statistics",
)
async def get_feed_stats(
    current_user: User = Depends(get_current_user),
    service: NewsfeedService = Depends(get_newsfeed_service),
):
    """
    Get feed statistics for current user

    Returns:
    - total_items: Number of items in feed
    - last_updated: When feed was last updated
    - cache_status: Whether feed is cached ("hit" or "miss")
    """
    try:
        stats = await service.get_feed_stats(current_user.id)

        return FeedStatsResponse(
            user_id=stats["user_id"],
            total_items=stats["total_items"],
            last_updated=stats["last_updated"],
            cache_status=stats["cache_status"],
        )

    except Exception as e:
        logger.error(f"Error getting feed stats for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve feed statistics"
        )


# Admin/Internal endpoints (for testing and debugging)
@app.post(
    "/internal/feed/fanout/{post_id}",
    response_model=MessageResponse,
    tags=["Internal"],
    summary="Fan-out post to followers (internal)",
    include_in_schema=settings.DEBUG,
)
async def fanout_post(
    post_id: str,
    post_user_id: int = Query(..., description="User ID who created the post"),
    current_user: User = Depends(get_current_user),
    service: NewsfeedService = Depends(get_newsfeed_service),
    authorization: Optional[str] = Header(None),
):
    """
    Internal endpoint to manually fan-out a post to followers' feeds

    Only available in DEBUG mode
    """
    try:
        from datetime import datetime

        # Extract token
        token = authorization.replace("Bearer ", "") if authorization else None

        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required"
            )

        count = await service.add_post_to_followers_feeds(
            post_id,
            post_user_id,
            datetime.utcnow(),
            token
        )

        return MessageResponse(
            message=f"Post {post_id} added to {count} followers' feeds"
        )

    except Exception as e:
        logger.error(f"Error in fanout: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fan-out post"
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "newsfeed_service.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
