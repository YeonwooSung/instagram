"""
Database connection and utilities
"""
import asyncpg
from typing import Optional
from config import settings


class Database:
    """Database connection manager"""

    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self):
        """Create database connection pool"""
        self.pool = await asyncpg.create_pool(
            settings.DATABASE_URL,
            min_size=1,
            max_size=settings.DB_POOL_SIZE,
            command_timeout=60,
        )
        print(f"✓ Database pool created with size {settings.DB_POOL_SIZE}")

    async def disconnect(self):
        """Close database connection pool"""
        if self.pool:
            await self.pool.close()
            print("✓ Database pool closed")

    async def fetch_one(self, query: str, *args):
        """Fetch a single row"""
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def fetch_all(self, query: str, *args):
        """Fetch all rows"""
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def execute(self, query: str, *args):
        """Execute a query without returning results"""
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)


# Global database instance
db = Database()


async def get_db():
    """Dependency for getting database connection"""
    return db
