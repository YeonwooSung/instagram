"""
Pydantic schemas for request/response validation
"""
from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import datetime
from enum import Enum


class FollowStatus(str, Enum):
    """Follow relationship status"""

    ACCEPTED = "accepted"
    PENDING = "pending"
    REJECTED = "rejected"


class RelationshipType(str, Enum):
    """Relationship type between users"""

    FOLLOWING = "following"  # Current user follows target user
    FOLLOWED_BY = "followed_by"  # Target user follows current user
    MUTUAL = "mutual"  # Both follow each other
    PENDING = "pending"  # Current user sent follow request
    REQUESTED = "requested"  # Target user sent follow request
    NONE = "none"  # No relationship


# Request Schemas
class FollowRequest(BaseModel):
    """Request to follow a user"""

    pass  # user_id comes from path parameter


class UnfollowRequest(BaseModel):
    """Request to unfollow a user"""

    pass  # user_id comes from path parameter


class FollowRequestAction(BaseModel):
    """Accept or reject follow request"""

    action: str = Field(..., description="Action: 'accept' or 'reject'")

    @validator("action")
    def validate_action(cls, v):
        if v not in ["accept", "reject"]:
            raise ValueError("Action must be 'accept' or 'reject'")
        return v


# Response Schemas
class MessageResponse(BaseModel):
    """Generic message response"""

    message: str


class FollowResponse(BaseModel):
    """Response after follow action"""

    success: bool
    status: FollowStatus
    message: str


class UserFollowInfo(BaseModel):
    """User follow information"""

    user_id: int
    created_at: datetime


class FollowersResponse(BaseModel):
    """Response with followers list"""

    followers: List[UserFollowInfo]
    total: int
    page: int
    page_size: int
    has_more: bool


class FollowingResponse(BaseModel):
    """Response with following list"""

    following: List[UserFollowInfo]
    total: int
    page: int
    page_size: int
    has_more: bool


class PendingRequestsResponse(BaseModel):
    """Response with pending follow requests"""

    requests: List[UserFollowInfo]
    total: int
    page: int
    page_size: int
    has_more: bool


class RelationshipResponse(BaseModel):
    """Response with relationship info between two users"""

    user_id: int
    target_user_id: int
    relationship: RelationshipType
    is_following: bool
    is_followed_by: bool
    is_mutual: bool
    is_pending: bool
    is_requested: bool


class GraphStatsResponse(BaseModel):
    """User's graph statistics"""

    user_id: int
    follower_count: int
    following_count: int
    pending_requests_count: int
    mutual_friends_count: Optional[int] = None


class MutualFollowersResponse(BaseModel):
    """Response with mutual followers"""

    user_id: int
    other_user_id: int
    mutual_followers: List[int]
    count: int


class FollowSuggestionsResponse(BaseModel):
    """Response with follow suggestions"""

    suggestions: List[int]
    count: int


# Internal Models
class User(BaseModel):
    """User model from Auth Service"""

    id: int
    username: str
    email: str
    full_name: Optional[str] = None
    is_private: bool = False
    is_verified: bool = False
    is_active: bool = True


class FollowRelationship(BaseModel):
    """Follow relationship model"""

    follower_id: int
    following_id: int
    status: FollowStatus
    created_at: datetime
