"""
Domain models - Core business entities
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from enum import Enum


class MediaType(str, Enum):
    """Media type enumeration"""
    IMAGE = "image"
    VIDEO = "video"


@dataclass
class Media:
    """Media domain model"""
    id: int
    user_id: int
    post_id: Optional[int]
    media_type: MediaType
    file_path: str
    thumbnail_path: Optional[str]
    width: Optional[int]
    height: Optional[int]
    file_size: int
    mime_type: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def is_owner(self, user_id: int) -> bool:
        """Check if the given user_id is the owner of this media"""
        return self.user_id == user_id

    def get_url(self, base_url: str) -> str:
        """Get media URL"""
        return f"{base_url}/{self.file_path}"

    def get_thumbnail_url(self, base_url: str) -> Optional[str]:
        """Get thumbnail URL"""
        if self.thumbnail_path:
            return f"{base_url}/{self.thumbnail_path}"
        return None


@dataclass
class MediaUploadResult:
    """Result of media upload operation"""
    media_id: int
    media_url: str
    thumbnail_url: Optional[str]
    width: Optional[int]
    height: Optional[int]
    file_size: int
