"""
Database connection and operations
"""
import asyncpg
from typing import Optional, List, Dict, Any
from datetime import datetime
import logging

from .config import settings

logger = logging.getLogger(__name__)


class Database:
    """PostgreSQL database connection manager using asyncpg"""

    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self):
        """Create database connection pool"""
        try:
            self.pool = await asyncpg.create_pool(
                settings.DATABASE_URL,
                min_size=1,
                max_size=settings.DB_POOL_SIZE,
                command_timeout=60,
            )
            logger.info("Database connection pool created successfully")
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise

    async def disconnect(self):
        """Close database connection pool"""
        if self.pool:
            await self.pool.close()
            logger.info("Database connection pool closed")

    async def fetch_one(self, query: str, *args) -> Optional[Dict[str, Any]]:
        """Fetch a single row"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, *args)
            return dict(row) if row else None

    async def fetch_all(self, query: str, *args) -> List[Dict[str, Any]]:
        """Fetch all rows"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *args)
            return [dict(row) for row in rows]

    async def execute(self, query: str, *args) -> str:
        """Execute a query"""
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)

    async def execute_many(self, query: str, args_list: List[tuple]) -> None:
        """Execute multiple queries in a transaction"""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.executemany(query, args_list)

    async def transaction(self):
        """Get a transaction context"""
        conn = await self.pool.acquire()
        return conn.transaction()

    # Graph-specific queries
    async def create_follow(
        self, follower_id: int, following_id: int, status: str = "accepted"
    ) -> bool:
        """Create a follow relationship"""
        query = """
            INSERT INTO follows (follower_id, following_id, status, created_at)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (follower_id, following_id) DO NOTHING
            RETURNING follower_id
        """
        result = await self.fetch_one(
            query, follower_id, following_id, status, datetime.utcnow()
        )
        return result is not None

    async def delete_follow(self, follower_id: int, following_id: int) -> bool:
        """Delete a follow relationship"""
        query = """
            DELETE FROM follows
            WHERE follower_id = $1 AND following_id = $2
            RETURNING follower_id
        """
        result = await self.fetch_one(query, follower_id, following_id)
        return result is not None

    async def update_follow_status(
        self, follower_id: int, following_id: int, status: str
    ) -> bool:
        """Update follow request status"""
        query = """
            UPDATE follows
            SET status = $3
            WHERE follower_id = $1 AND following_id = $2
            RETURNING follower_id
        """
        result = await self.fetch_one(query, follower_id, following_id, status)
        return result is not None

    async def get_follow_relationship(
        self, follower_id: int, following_id: int
    ) -> Optional[Dict[str, Any]]:
        """Get follow relationship status"""
        query = """
            SELECT follower_id, following_id, status, created_at
            FROM follows
            WHERE follower_id = $1 AND following_id = $2
        """
        return await self.fetch_one(query, follower_id, following_id)

    async def get_followers(
        self, user_id: int, limit: int = 20, offset: int = 0, status: str = "accepted"
    ) -> List[Dict[str, Any]]:
        """Get user's followers"""
        query = """
            SELECT follower_id, status, created_at
            FROM follows
            WHERE following_id = $1 AND status = $2
            ORDER BY created_at DESC
            LIMIT $3 OFFSET $4
        """
        return await self.fetch_all(query, user_id, status, limit, offset)

    async def get_following(
        self, user_id: int, limit: int = 20, offset: int = 0, status: str = "accepted"
    ) -> List[Dict[str, Any]]:
        """Get users that user is following"""
        query = """
            SELECT following_id, status, created_at
            FROM follows
            WHERE follower_id = $1 AND status = $2
            ORDER BY created_at DESC
            LIMIT $3 OFFSET $4
        """
        return await self.fetch_all(query, user_id, status, limit, offset)

    async def get_follower_count(self, user_id: int, status: str = "accepted") -> int:
        """Get follower count"""
        query = """
            SELECT COUNT(*) as count
            FROM follows
            WHERE following_id = $1 AND status = $2
        """
        result = await self.fetch_one(query, user_id, status)
        return result["count"] if result else 0

    async def get_following_count(self, user_id: int, status: str = "accepted") -> int:
        """Get following count"""
        query = """
            SELECT COUNT(*) as count
            FROM follows
            WHERE follower_id = $1 AND status = $2
        """
        result = await self.fetch_one(query, user_id, status)
        return result["count"] if result else 0

    async def get_pending_requests(
        self, user_id: int, limit: int = 20, offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get pending follow requests for user"""
        query = """
            SELECT follower_id, created_at
            FROM follows
            WHERE following_id = $1 AND status = 'pending'
            ORDER BY created_at DESC
            LIMIT $2 OFFSET $3
        """
        return await self.fetch_all(query, user_id, limit, offset)

    async def check_mutual_follow(self, user_id: int, other_user_id: int) -> bool:
        """Check if two users follow each other"""
        query = """
            SELECT EXISTS(
                SELECT 1 FROM follows WHERE follower_id = $1 AND following_id = $2 AND status = 'accepted'
            ) AND EXISTS(
                SELECT 1 FROM follows WHERE follower_id = $2 AND following_id = $1 AND status = 'accepted'
            ) as is_mutual
        """
        result = await self.fetch_one(query, user_id, other_user_id)
        return result["is_mutual"] if result else False

    async def get_mutual_followers(
        self, user_id: int, other_user_id: int, limit: int = 20
    ) -> List[int]:
        """Get mutual followers between two users"""
        query = """
            SELECT f1.follower_id
            FROM follows f1
            INNER JOIN follows f2 ON f1.follower_id = f2.follower_id
            WHERE f1.following_id = $1 AND f2.following_id = $2
              AND f1.status = 'accepted' AND f2.status = 'accepted'
            LIMIT $3
        """
        results = await self.fetch_all(query, user_id, other_user_id, limit)
        return [row["follower_id"] for row in results]

    async def get_follow_suggestions(
        self, user_id: int, limit: int = 10
    ) -> List[int]:
        """Get follow suggestions (friends of friends)"""
        query = """
            WITH user_following AS (
                SELECT following_id FROM follows
                WHERE follower_id = $1 AND status = 'accepted'
            ),
            friends_of_friends AS (
                SELECT f.following_id, COUNT(*) as mutual_count
                FROM follows f
                WHERE f.follower_id IN (SELECT following_id FROM user_following)
                  AND f.following_id != $1
                  AND f.following_id NOT IN (SELECT following_id FROM user_following)
                  AND f.status = 'accepted'
                GROUP BY f.following_id
                ORDER BY mutual_count DESC
                LIMIT $2
            )
            SELECT following_id FROM friends_of_friends
        """
        results = await self.fetch_all(query, user_id, limit)
        return [row["following_id"] for row in results]


# Global database instance
db = Database()


async def get_db() -> Database:
    """Dependency for getting database instance"""
    return db
