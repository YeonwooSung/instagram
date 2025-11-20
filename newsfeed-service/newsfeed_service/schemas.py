"""
Pydantic schemas for Newsfeed Service
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


# User schema (from auth service)
class User(BaseModel):
    """User model from auth service"""
    id: int
    username: str
    email: Optional[str] = None


# Feed Item schemas
class FeedItem(BaseModel):
    """Feed item model"""
    id: int
    user_id: int
    post_id: str
    post_user_id: int
    post_created_at: datetime
    feed_score: Optional[float] = 0.0
    created_at: datetime

    class Config:
        from_attributes = True


class FeedItemResponse(BaseModel):
    """Feed item response with post details"""
    id: int
    post_id: str
    post_user_id: int
    post_created_at: datetime
    feed_score: Optional[float] = 0.0
    created_at: datetime
    # Post details (fetched from post service)
    post_data: Optional[Dict[str, Any]] = None


class FeedResponse(BaseModel):
    """Feed response with pagination"""
    items: List[FeedItemResponse]
    total: int
    page: int
    page_size: int
    has_more: bool
    next_cursor: Optional[str] = None


class FeedMetadata(BaseModel):
    """Feed metadata"""
    user_id: int
    last_updated: Optional[datetime] = None
    total_items: int = 0
    is_stale: bool = False


# Message responses
class MessageResponse(BaseModel):
    """Generic message response"""
    message: str


class FeedStatsResponse(BaseModel):
    """Feed statistics response"""
    user_id: int
    total_items: int
    last_updated: Optional[datetime] = None
    cache_status: str  # "hit", "miss", "stale"


# Kafka event schemas
class PostCreatedEvent(BaseModel):
    """Post created event from Kafka"""
    event_type: str
    post_id: str
    user_id: int
    post_data: Dict[str, Any]
    timestamp: str


class PostDeletedEvent(BaseModel):
    """Post deleted event from Kafka"""
    event_type: str
    post_id: str
    user_id: int


class FollowAcceptedEvent(BaseModel):
    """Follow accepted event from Kafka"""
    event_type: str
    follower_id: int
    following_id: int
    timestamp: str


class UnfollowEvent(BaseModel):
    """Unfollow event from Kafka"""
    event_type: str
    follower_id: int
    following_id: int
