"""
Repository implementations - Data access layer
"""
from typing import Optional, List
import asyncpg

from domain.models import Media, MediaType
from domain.repositories import IMediaRepository
from .connection import DatabaseConnection


class MediaRepository(IMediaRepository):
    """Media repository implementation using PostgreSQL"""

    def __init__(self, db: DatabaseConnection):
        self.db = db

    def _row_to_media(self, row: Optional[asyncpg.Record]) -> Optional[Media]:
        """Convert database row to Media model"""
        if not row:
            return None
        data = dict(row)
        data['media_type'] = MediaType(data['media_type'])
        return Media(**data)

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
        row = await self.db.fetch_one(
            """
            INSERT INTO media (user_id, post_id, media_type, file_path, thumbnail_path,
                             width, height, file_size, mime_type)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING id, user_id, post_id, media_type, file_path, thumbnail_path,
                      width, height, file_size, mime_type, created_at, updated_at
            """,
            user_id, post_id, media_type.value, file_path, thumbnail_path,
            width, height, file_size, mime_type
        )
        return self._row_to_media(row)

    async def find_by_id(self, media_id: int) -> Optional[Media]:
        """Find media by ID"""
        row = await self.db.fetch_one(
            """
            SELECT id, user_id, post_id, media_type, file_path, thumbnail_path,
                   width, height, file_size, mime_type, created_at, updated_at
            FROM media
            WHERE id = $1
            """,
            media_id
        )
        return self._row_to_media(row)

    async def find_by_post_id(self, post_id: int) -> List[Media]:
        """Find media by post ID"""
        rows = await self.db.fetch_all(
            """
            SELECT id, user_id, post_id, media_type, file_path, thumbnail_path,
                   width, height, file_size, mime_type, created_at, updated_at
            FROM media
            WHERE post_id = $1
            ORDER BY created_at ASC
            """,
            post_id
        )
        return [self._row_to_media(row) for row in rows]

    async def find_by_user_id(self, user_id: int, limit: int = 50, offset: int = 0) -> List[Media]:
        """Find media by user ID"""
        rows = await self.db.fetch_all(
            """
            SELECT id, user_id, post_id, media_type, file_path, thumbnail_path,
                   width, height, file_size, mime_type, created_at, updated_at
            FROM media
            WHERE user_id = $1
            ORDER BY created_at DESC
            LIMIT $2 OFFSET $3
            """,
            user_id, limit, offset
        )
        return [self._row_to_media(row) for row in rows]

    async def delete(self, media_id: int) -> None:
        """Delete media record"""
        await self.db.execute("DELETE FROM media WHERE id = $1", media_id)

    async def update_post_id(self, media_id: int, post_id: int) -> None:
        """Update media's post ID"""
        await self.db.execute(
            "UPDATE media SET post_id = $1 WHERE id = $2",
            post_id, media_id
        )
