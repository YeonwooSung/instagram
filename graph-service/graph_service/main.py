"""
FastAPI application for Graph Service
"""
from fastapi import FastAPI, Depends, HTTPException, status, Query
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

from .config import settings
from .database import db, get_db, Database
from .cache import cache, get_cache, RedisCache
from .kafka_producer import kafka_producer, get_kafka_producer, KafkaProducerManager
from .dependencies import get_current_user
from .service import GraphService
from .schemas import (
    User,
    FollowResponse,
    FollowersResponse,
    FollowingResponse,
    PendingRequestsResponse,
    RelationshipResponse,
    GraphStatsResponse,
    MutualFollowersResponse,
    FollowSuggestionsResponse,
    MessageResponse,
    FollowRequestAction,
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
    logger.info("Starting Graph Service...")

    # Connect to database
    await db.connect()
    logger.info("Database connected")

    # Connect to Redis
    await cache.connect()
    logger.info("Redis cache initialized")

    # Start Kafka producer
    await kafka_producer.start()
    logger.info("Kafka producer started")

    logger.info(f"Graph Service started successfully on port {settings.PORT}")

    yield

    # Shutdown
    logger.info("Shutting down Graph Service...")

    # Stop Kafka producer
    await kafka_producer.stop()

    # Disconnect Redis
    await cache.disconnect()

    # Disconnect database
    await db.disconnect()

    logger.info("Graph Service shut down successfully")


# Create FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Instagram Graph Service - Manages social graph relationships (follow/unfollow)",
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
def get_graph_service(
    db: Database = Depends(get_db),
    cache: RedisCache = Depends(get_cache),
    kafka: KafkaProducerManager = Depends(get_kafka_producer),
) -> GraphService:
    """Get GraphService instance with dependencies"""
    return GraphService(db, cache, kafka)


# Health check endpoint
@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": settings.APP_NAME}


# Follow/Unfollow endpoints
@app.post(
    "/api/v1/graph/follow/{user_id}",
    response_model=FollowResponse,
    tags=["Follow"],
    summary="Follow a user",
)
async def follow_user(
    user_id: int,
    current_user: User = Depends(get_current_user),
    service: GraphService = Depends(get_graph_service),
):
    """
    Follow a user

    - If the target user has a private account, a follow request will be sent
    - If the target user has a public account, you will immediately follow them
    """
    return await service.follow_user(current_user.id, user_id)


@app.delete(
    "/api/v1/graph/unfollow/{user_id}",
    response_model=FollowResponse,
    tags=["Follow"],
    summary="Unfollow a user",
)
async def unfollow_user(
    user_id: int,
    current_user: User = Depends(get_current_user),
    service: GraphService = Depends(get_graph_service),
):
    """
    Unfollow a user

    - Removes the follow relationship
    - Works for both accepted follows and pending requests
    """
    return await service.unfollow_user(current_user.id, user_id)


# Followers/Following endpoints
@app.get(
    "/api/v1/graph/followers/{user_id}",
    response_model=FollowersResponse,
    tags=["Followers"],
    summary="Get user's followers",
)
async def get_followers(
    user_id: int,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(
        settings.DEFAULT_PAGE_SIZE, ge=1, le=settings.MAX_PAGE_SIZE, description="Items per page"
    ),
    current_user: User = Depends(get_current_user),
    service: GraphService = Depends(get_graph_service),
):
    """
    Get a user's followers

    Returns paginated list of users who follow the specified user
    """
    followers, total, has_more = await service.get_followers(user_id, page, page_size)

    return FollowersResponse(
        followers=followers,
        total=total,
        page=page,
        page_size=page_size,
        has_more=has_more,
    )


@app.get(
    "/api/v1/graph/following/{user_id}",
    response_model=FollowingResponse,
    tags=["Following"],
    summary="Get users that user is following",
)
async def get_following(
    user_id: int,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(
        settings.DEFAULT_PAGE_SIZE, ge=1, le=settings.MAX_PAGE_SIZE, description="Items per page"
    ),
    current_user: User = Depends(get_current_user),
    service: GraphService = Depends(get_graph_service),
):
    """
    Get users that a user is following

    Returns paginated list of users that the specified user follows
    """
    following, total, has_more = await service.get_following(user_id, page, page_size)

    return FollowingResponse(
        following=following,
        total=total,
        page=page,
        page_size=page_size,
        has_more=has_more,
    )


# Relationship endpoints
@app.get(
    "/api/v1/graph/relationship/{user_id}",
    response_model=RelationshipResponse,
    tags=["Relationship"],
    summary="Get relationship with user",
)
async def get_relationship(
    user_id: int,
    current_user: User = Depends(get_current_user),
    service: GraphService = Depends(get_graph_service),
):
    """
    Get relationship between current user and target user

    Returns detailed information about the relationship:
    - following: Current user follows target user
    - followed_by: Target user follows current user
    - mutual: Both users follow each other
    - pending: Current user sent follow request to target user
    - requested: Target user sent follow request to current user
    - none: No relationship
    """
    return await service.get_relationship(current_user.id, user_id)


@app.get(
    "/api/v1/graph/stats/{user_id}",
    response_model=GraphStatsResponse,
    tags=["Stats"],
    summary="Get user's graph statistics",
)
async def get_user_stats(
    user_id: int,
    current_user: User = Depends(get_current_user),
    service: GraphService = Depends(get_graph_service),
):
    """
    Get user's graph statistics

    Returns:
    - follower_count: Number of followers
    - following_count: Number of users being followed
    - pending_requests_count: Number of pending follow requests (for private accounts)
    """
    return await service.get_user_stats(user_id)


# Follow requests endpoints
@app.get(
    "/api/v1/graph/requests/pending",
    response_model=PendingRequestsResponse,
    tags=["Follow Requests"],
    summary="Get pending follow requests",
)
async def get_pending_requests(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(
        settings.DEFAULT_PAGE_SIZE, ge=1, le=settings.MAX_PAGE_SIZE, description="Items per page"
    ),
    current_user: User = Depends(get_current_user),
    service: GraphService = Depends(get_graph_service),
):
    """
    Get pending follow requests

    Returns list of users who have requested to follow you (for private accounts)
    """
    requests, total, has_more = await service.get_pending_requests(
        current_user.id, page, page_size
    )

    return PendingRequestsResponse(
        requests=requests,
        total=total,
        page=page,
        page_size=page_size,
        has_more=has_more,
    )


@app.post(
    "/api/v1/graph/requests/{follower_id}",
    response_model=FollowResponse,
    tags=["Follow Requests"],
    summary="Accept or reject follow request",
)
async def handle_follow_request(
    follower_id: int,
    action: FollowRequestAction,
    current_user: User = Depends(get_current_user),
    service: GraphService = Depends(get_graph_service),
):
    """
    Accept or reject a follow request

    - action: 'accept' or 'reject'
    """
    if action.action == "accept":
        return await service.accept_follow_request(current_user.id, follower_id)
    else:
        return await service.reject_follow_request(current_user.id, follower_id)


# Mutual followers endpoint
@app.get(
    "/api/v1/graph/mutual/{user_id}",
    response_model=MutualFollowersResponse,
    tags=["Mutual"],
    summary="Get mutual followers",
)
async def get_mutual_followers(
    user_id: int,
    limit: int = Query(20, ge=1, le=100, description="Maximum number of results"),
    current_user: User = Depends(get_current_user),
    service: GraphService = Depends(get_graph_service),
):
    """
    Get mutual followers between current user and target user

    Returns list of users who follow both the current user and the target user
    """
    mutual_followers = await service.get_mutual_followers(
        current_user.id, user_id, limit
    )

    return MutualFollowersResponse(
        user_id=current_user.id,
        other_user_id=user_id,
        mutual_followers=mutual_followers,
        count=len(mutual_followers),
    )


# Follow suggestions endpoint
@app.get(
    "/api/v1/graph/suggestions",
    response_model=FollowSuggestionsResponse,
    tags=["Suggestions"],
    summary="Get follow suggestions",
)
async def get_follow_suggestions(
    limit: int = Query(10, ge=1, le=50, description="Maximum number of suggestions"),
    current_user: User = Depends(get_current_user),
    service: GraphService = Depends(get_graph_service),
):
    """
    Get follow suggestions

    Returns suggested users to follow based on:
    - Friends of friends (users followed by people you follow)
    - Ordered by number of mutual connections
    """
    suggestions = await service.get_follow_suggestions(current_user.id, limit)

    return FollowSuggestionsResponse(
        suggestions=suggestions,
        count=len(suggestions),
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "graph_service.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
