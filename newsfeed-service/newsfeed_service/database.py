"""
Database connection and operations for Newsfeed Service
"""
import asyncpg
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
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

            # Initialize schema
            await self._init_schema()
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise

    async def disconnect(self):
        """Close database connection pool"""
        if self.pool:
            await self.pool.close()
            logger.info("Database connection pool closed")

    async def _init_schema(self):
        """Initialize database schema"""
        async with self.pool.acquire() as conn:
            # Create feed_items table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS feed_items (
                    id BIGSERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    post_id VARCHAR(24) NOT NULL,
                    post_user_id INTEGER NOT NULL,
                    post_created_at TIMESTAMP NOT NULL,
                    feed_score DOUBLE PRECISION DEFAULT 0.0,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)

            # Create indexes
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_feed_items_user_created
                ON feed_items (user_id, post_created_at DESC)
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_feed_items_post
                ON feed_items (post_id)
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_feed_items_user_post
                ON feed_items (user_id, post_id)
            """)

            # Create feed_metadata table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS feed_metadata (
                    user_id INTEGER PRIMARY KEY,
                    last_updated TIMESTAMP,
                    total_items INTEGER DEFAULT 0,
                    is_stale BOOLEAN DEFAULT FALSE
                )
            """)

            logger.info("Database schema initialized successfully")

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

    # Feed-specific queries
    async def add_feed_item(
        self,
        user_id: int,
        post_id: str,
        post_user_id: int,
        post_created_at: datetime,
        feed_score: float = 0.0
    ) -> Optional[Dict[str, Any]]:
        """Add item to user's feed"""
        query = """
            INSERT INTO feed_items (user_id, post_id, post_user_id, post_created_at, feed_score)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT DO NOTHING
            RETURNING id, user_id, post_id, post_user_id, post_created_at, feed_score, created_at
        """
        return await self.fetch_one(
            query, user_id, post_id, post_user_id, post_created_at, feed_score
        )

    async def add_feed_items_bulk(self, items: List[tuple]) -> int:
        """Add multiple feed items in bulk"""
        query = """
            INSERT INTO feed_items (user_id, post_id, post_user_id, post_created_at, feed_score)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT DO NOTHING
        """
        try:
            await self.execute_many(query, items)
            return len(items)
        except Exception as e:
            logger.error(f"Failed to add bulk feed items: {e}")
            return 0

    async def remove_feed_item(self, user_id: int, post_id: str) -> bool:
        """Remove item from user's feed"""
        query = """
            DELETE FROM feed_items
            WHERE user_id = $1 AND post_id = $2
            RETURNING id
        """
        result = await self.fetch_one(query, user_id, post_id)
        return result is not None

    async def remove_feed_items_by_post(self, post_id: str) -> int:
        """Remove post from all users' feeds"""
        query = """
            DELETE FROM feed_items
            WHERE post_id = $1
        """
        result = await self.execute(query, post_id)
        # Parse result like "DELETE 10" to get count
        count = int(result.split()[-1]) if result else 0
        return count

    async def remove_feed_items_by_author(self, user_id: int, post_user_id: int) -> int:
        """Remove all posts from a specific author from user's feed"""
        query = """
            DELETE FROM feed_items
            WHERE user_id = $1 AND post_user_id = $2
        """
        result = await self.execute(query, user_id, post_user_id)
        count = int(result.split()[-1]) if result else 0
        return count

    async def get_feed_items(
        self,
        user_id: int,
        limit: int = 20,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get user's feed items with pagination"""
        query = """
            SELECT id, user_id, post_id, post_user_id, post_created_at, feed_score, created_at
            FROM feed_items
            WHERE user_id = $1
            ORDER BY post_created_at DESC, feed_score DESC
            LIMIT $2 OFFSET $3
        """
        return await self.fetch_all(query, user_id, limit, offset)

    async def get_feed_count(self, user_id: int) -> int:
        """Get total feed items count for user"""
        query = """
            SELECT COUNT(*) as count
            FROM feed_items
            WHERE user_id = $1
        """
        result = await self.fetch_one(query, user_id)
        return result["count"] if result else 0

    async def cleanup_old_feed_items(self, user_id: int, max_items: int) -> int:
        """Remove oldest feed items if exceeding max limit"""
        query = """
            DELETE FROM feed_items
            WHERE id IN (
                SELECT id FROM feed_items
                WHERE user_id = $1
                ORDER BY post_created_at DESC, feed_score DESC
                OFFSET $2
            )
        """
        result = await self.execute(query, user_id, max_items)
        count = int(result.split()[-1]) if result else 0
        return count

    async def update_feed_metadata(
        self,
        user_id: int,
        total_items: Optional[int] = None,
        is_stale: Optional[bool] = None
    ) -> None:
        """Update feed metadata"""
        if total_items is None:
            total_items = await self.get_feed_count(user_id)

        query = """
            INSERT INTO feed_metadata (user_id, last_updated, total_items, is_stale)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (user_id)
            DO UPDATE SET
                last_updated = $2,
                total_items = $3,
                is_stale = COALESCE($4, feed_metadata.is_stale)
        """
        await self.execute(
            query,
            user_id,
            datetime.utcnow(),
            total_items,
            is_stale if is_stale is not None else False
        )

    async def get_feed_metadata(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get feed metadata"""
        query = """
            SELECT user_id, last_updated, total_items, is_stale
            FROM feed_metadata
            WHERE user_id = $1
        """
        return await self.fetch_one(query, user_id)

    async def mark_feed_stale(self, user_id: int) -> None:
        """Mark user's feed as stale"""
        query = """
            UPDATE feed_metadata
            SET is_stale = TRUE
            WHERE user_id = $1
        """
        await self.execute(query, user_id)


# Global database instance
db = Database()


async def get_db() -> Database:
    """Dependency for getting database instance"""
    return db
