"""
Pydantic schemas for Post Service
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from bson import ObjectId


class PyObjectId(ObjectId):
    """Custom type for MongoDB ObjectId"""

    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return ObjectId(v)

    @classmethod
    def __get_pydantic_json_schema__(cls, field_schema):
        field_schema.update(type="string")


class PostCreate(BaseModel):
    """Post creation request"""
    caption: Optional[str] = Field(None, max_length=2200)
    media_ids: List[int] = Field(..., min_items=1, max_items=10, description="Media file IDs from media service")
    location: Optional[str] = Field(None, max_length=255)
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    hashtags: Optional[List[str]] = Field(None, max_items=30)
    mentions: Optional[List[str]] = Field(None, max_items=20)
    is_comments_disabled: bool = False
    is_hidden: bool = False


class PostUpdate(BaseModel):
    """Post update request"""
    caption: Optional[str] = Field(None, max_length=2200)
    location: Optional[str] = Field(None, max_length=255)
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    hashtags: Optional[List[str]] = Field(None, max_items=30)
    is_comments_disabled: Optional[bool] = None
    is_hidden: Optional[bool] = None


class PostResponse(BaseModel):
    """Post response"""
    id: str = Field(alias="_id")
    user_id: int
    caption: Optional[str] = None
    media_ids: List[int]
    location: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    hashtags: List[str] = []
    mentions: List[str] = []
    like_count: int = 0
    comment_count: int = 0
    share_count: int = 0
    view_count: int = 0
    is_comments_disabled: bool = False
    is_hidden: bool = False
    created_at: datetime
    updated_at: datetime

    class Config:
        populate_by_name = True
        json_encoders = {ObjectId: str}


class PostDetailResponse(PostResponse):
    """Detailed post response with user info"""
    username: Optional[str] = None
    user_profile_image: Optional[str] = None
    media_urls: List[dict] = []
    is_liked: bool = False
    is_saved: bool = False


class PostListResponse(BaseModel):
    """Post list response"""
    posts: List[PostResponse]
    total: int
    page: int
    page_size: int
    has_more: bool


class LikeResponse(BaseModel):
    """Like action response"""
    post_id: str
    is_liked: bool
    like_count: int


class CommentCreate(BaseModel):
    """Comment creation request"""
    content: str = Field(..., min_length=1, max_length=500)
    parent_comment_id: Optional[str] = None


class CommentResponse(BaseModel):
    """Comment response"""
    id: str = Field(alias="_id")
    post_id: str
    user_id: int
    username: str
    user_profile_image: Optional[str] = None
    content: str
    parent_comment_id: Optional[str] = None
    like_count: int = 0
    reply_count: int = 0
    is_liked: bool = False
    created_at: datetime
    updated_at: datetime

    class Config:
        populate_by_name = True
        json_encoders = {ObjectId: str}


class CommentListResponse(BaseModel):
    """Comment list response"""
    comments: List[CommentResponse]
    total: int
    page: int
    page_size: int


class MessageResponse(BaseModel):
    """Generic message response"""
    message: str
    success: bool = True


class ErrorResponse(BaseModel):
    """Error response"""
    error: str
    detail: Optional[str] = None
    success: bool = False


class StatsResponse(BaseModel):
    """Post statistics response"""
    total_posts: int
    total_likes: int
    total_comments: int
    total_views: int
    avg_engagement_rate: float
