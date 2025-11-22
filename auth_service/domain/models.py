"""
Domain models - Core business entities
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class User:
    """User domain model"""
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
    is_active: bool = True
    follower_count: int = 0
    following_count: int = 0
    post_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None
    password_hash: Optional[str] = None

    def is_owner(self, user_id: int) -> bool:
        """Check if the given user_id is the owner of this profile"""
        return self.id == user_id

    def can_view_private_info(self, requester_id: Optional[int]) -> bool:
        """Check if requester can view private information"""
        if requester_id is None:
            return False
        return self.id == requester_id

    def hide_private_info(self):
        """Hide private information for non-owners"""
        self.email = None
        self.phone_number = None
        self.password_hash = None


@dataclass
class RefreshToken:
    """Refresh token domain model"""
    id: int
    user_id: int
    token_hash: str
    expires_at: datetime
    is_revoked: bool = False
    created_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None

    def is_valid(self) -> bool:
        """Check if the refresh token is valid"""
        if self.is_revoked:
            return False
        if self.expires_at < datetime.utcnow():
            return False
        return True
