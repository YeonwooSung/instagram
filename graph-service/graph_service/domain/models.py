"""
Domain models - Core business entities
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from enum import Enum


class FollowStatus(str, Enum):
    """Follow relationship status"""
    FOLLOWING = "following"
    NOT_FOLLOWING = "not_following"
    REQUESTED = "requested"
    BLOCKED = "blocked"


class RelationshipType(str, Enum):
    """Type of relationship between users"""
    FOLLOWER = "follower"
    FOLLOWING = "following"
    MUTUAL = "mutual"
    NONE = "none"


@dataclass
class FollowRelationship:
    """Follow relationship domain model"""
    follower_id: int
    following_id: int
    status: FollowStatus
    created_at: Optional[datetime] = None

    def is_mutual(self, reverse_exists: bool) -> bool:
        """Check if this is a mutual follow relationship"""
        return self.status == FollowStatus.FOLLOWING and reverse_exists

    def is_pending(self) -> bool:
        """Check if follow request is pending"""
        return self.status == FollowStatus.REQUESTED


@dataclass
class UserConnection:
    """User connection with relationship info"""
    user_id: int
    username: str
    full_name: Optional[str]
    profile_image_url: Optional[str]
    is_verified: bool
    relationship_type: RelationshipType
    followed_at: Optional[datetime] = None


@dataclass
class FollowStats:
    """Follow statistics for a user"""
    user_id: int
    follower_count: int
    following_count: int
    mutual_count: int
