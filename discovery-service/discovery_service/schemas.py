"""
Pydantic schemas for Discovery Service
"""
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class UserSearchResult(BaseModel):
    """User search result"""
    id: int
    username: str
    full_name: Optional[str] = None
    bio: Optional[str] = None
    profile_image_url: Optional[str] = None
    is_verified: bool = False
    is_private: bool = False
    follower_count: int = 0
    following_count: int = 0
    post_count: int = 0


class HashtagResult(BaseModel):
    """Hashtag search result"""
    id: int
    name: str
    post_count: int
    created_at: datetime


class PostSummary(BaseModel):
    """Post summary for discovery"""
    id: int
    user_id: int
    username: str
    user_profile_image: Optional[str] = None
    caption: Optional[str] = None
    image_url: Optional[str] = None
    video_url: Optional[str] = None
    like_count: int = 0
    comment_count: int = 0
    created_at: datetime


class TrendingPostsResponse(BaseModel):
    """Trending posts response"""
    posts: List[PostSummary]
    total: int
    page: int
    page_size: int


class UserSearchResponse(BaseModel):
    """User search response"""
    users: List[UserSearchResult]
    total: int
    page: int
    page_size: int


class HashtagSearchResponse(BaseModel):
    """Hashtag search response"""
    hashtags: List[HashtagResult]
    posts_preview: List[PostSummary]
    total: int


class RecommendedUsersResponse(BaseModel):
    """Recommended users response"""
    users: List[UserSearchResult]
    reason: str = "Based on your activity"


class LocationPostsResponse(BaseModel):
    """Location-based posts response"""
    location: str
    posts: List[PostSummary]
    total: int


class DiscoveryFeedResponse(BaseModel):
    """Discovery feed response"""
    posts: List[PostSummary]
    page: int
    page_size: int
    has_more: bool
