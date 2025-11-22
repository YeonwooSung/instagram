"""
Repository interfaces - Define contracts for data access
"""
from abc import ABC, abstractmethod
from typing import Optional, List
from .models import Media, MediaType


class IMediaRepository(ABC):
    """Media repository interface"""

    @abstractmethod
    async def create(
        self,
        user_id: int,
        post_id: Optional[int],
        media_type: MediaType,
        file_path: str,
        thumbnail_path: Optional[str],
        width: Optional[int],
        height: Optional[int],
        file_size: int,
        mime_type: str
    ) -> Media:
        """Create a new media record"""
        pass

    @abstractmethod
    async def find_by_id(self, media_id: int) -> Optional[Media]:
        """Find media by ID"""
        pass

    @abstractmethod
    async def find_by_post_id(self, post_id: int) -> List[Media]:
        """Find media by post ID"""
        pass

    @abstractmethod
    async def find_by_user_id(self, user_id: int, limit: int = 50, offset: int = 0) -> List[Media]:
        """Find media by user ID"""
        pass

    @abstractmethod
    async def delete(self, media_id: int) -> None:
        """Delete media record"""
        pass

    @abstractmethod
    async def update_post_id(self, media_id: int, post_id: int) -> None:
        """Update media's post ID"""
        pass
