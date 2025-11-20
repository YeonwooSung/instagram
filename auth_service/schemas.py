"""
Pydantic schemas for request/response validation
"""
from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional
from datetime import datetime
import re


class UserRegister(BaseModel):
    """User registration request"""
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: Optional[str] = Field(None, max_length=100)
    phone_number: Optional[str] = None

    @validator('username')
    def validate_username(cls, v):
        """Validate username format"""
        if not re.match(r'^[a-zA-Z0-9_\.]+$', v):
            raise ValueError('Username can only contain letters, numbers, underscores, and dots')
        return v.lower()

    @validator('phone_number')
    def validate_phone_number(cls, v):
        """Validate phone number format"""
        if v and not re.match(r'^\+?[1-9]\d{1,14}$', v):
            raise ValueError('Invalid phone number format')
        return v


class UserLogin(BaseModel):
    """User login request"""
    username_or_email: str
    password: str


class TokenResponse(BaseModel):
    """Token response"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshTokenRequest(BaseModel):
    """Refresh token request"""
    refresh_token: str


class UserProfile(BaseModel):
    """User profile response"""
    id: int
    username: str
    email: str
    full_name: Optional[str] = None
    bio: Optional[str] = None
    profile_image_url: Optional[str] = None
    website: Optional[str] = None
    phone_number: Optional[str] = None
    is_verified: bool = False
    is_private: bool = False
    follower_count: int = 0
    following_count: int = 0
    post_count: int = 0
    created_at: datetime
    last_seen_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class UpdateProfile(BaseModel):
    """Update profile request"""
    full_name: Optional[str] = Field(None, max_length=100)
    bio: Optional[str] = Field(None, max_length=500)
    website: Optional[str] = Field(None, max_length=255)
    phone_number: Optional[str] = None
    is_private: Optional[bool] = None

    @validator('website')
    def validate_website(cls, v):
        """Validate website URL"""
        if v and not re.match(r'^https?://.+', v):
            raise ValueError('Website must be a valid URL starting with http:// or https://')
        return v


class ChangePassword(BaseModel):
    """Change password request"""
    old_password: str
    new_password: str = Field(..., min_length=8)


class PasswordResetRequest(BaseModel):
    """Password reset request"""
    email: EmailStr


class PasswordReset(BaseModel):
    """Password reset with token"""
    token: str
    new_password: str = Field(..., min_length=8)


class MessageResponse(BaseModel):
    """Generic message response"""
    message: str
    success: bool = True


class ErrorResponse(BaseModel):
    """Error response"""
    error: str
    detail: Optional[str] = None
    success: bool = False
