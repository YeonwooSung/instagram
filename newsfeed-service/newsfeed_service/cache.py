"""
Redis cache for Newsfeed Service
"""
import redis.asyncio as redis
from typing import Optional, List, Tuple
import logging
import json
from datetime import datetime

from .config import settings

logger = logging.getLogger(__name__)


class RedisCache:
    """Redis cache manager for feed timeline"""

    def __init__(self):
        self.client: Optional[redis.Redis] = None

    async def connect(self):
        """Connect to Redis"""
        if not settings.REDIS_ENABLED:
            logger.warning("Redis is disabled")
            return

        try:
            self.client = await redis.from_url(
                f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}",
                password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
                encoding="utf-8",
                decode_responses=True,
            )
            # Test connection
            await self.client.ping()
            logger.info("Redis cache connected successfully")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self.client = None

    async def disconnect(self):
        """Disconnect from Redis"""
        if self.client:
            await self.client.close()
            logger.info("Redis cache disconnected")

    def _feed_key(self, user_id: int) -> str:
        """Get Redis key for user's feed timeline"""
        return f"feed:{user_id}"

    def _feed_metadata_key(self, user_id: int) -> str:
        """Get Redis key for user's feed metadata"""
        return f"feed:meta:{user_id}"

    async def add_to_feed(
        self,
        user_id: int,
        post_id: str,
        timestamp: float
    ) -> bool:
        """Add post to user's feed timeline (sorted set by timestamp)"""
        if not self.client:
            return False

        try:
            key = self._feed_key(user_id)
            await self.client.zadd(key, {post_id: timestamp})
            await self.client.expire(key, settings.FEED_CACHE_TTL)
            return True
        except Exception as e:
            logger.error(f"Failed to add to feed cache: {e}")
            return False

    async def add_to_feed_bulk(
        self,
        user_id: int,
        items: List[Tuple[str, float]]
    ) -> bool:
        """Add multiple posts to user's feed timeline"""
        if not self.client or not items:
            return False

        try:
            key = self._feed_key(user_id)
            mapping = {post_id: score for post_id, score in items}
            await self.client.zadd(key, mapping)
            await self.client.expire(key, settings.FEED_CACHE_TTL)
            return True
        except Exception as e:
            logger.error(f"Failed to add bulk to feed cache: {e}")
            return False

    async def remove_from_feed(self, user_id: int, post_id: str) -> bool:
        """Remove post from user's feed timeline"""
        if not self.client:
            return False

        try:
            key = self._feed_key(user_id)
            await self.client.zrem(key, post_id)
            return True
        except Exception as e:
            logger.error(f"Failed to remove from feed cache: {e}")
            return False

    async def get_feed(
        self,
        user_id: int,
        start: int = 0,
        end: int = 19
    ) -> List[str]:
        """Get user's feed timeline (newest first)"""
        if not self.client:
            return []

        try:
            key = self._feed_key(user_id)
            # ZREVRANGE returns in descending order (newest first)
            post_ids = await self.client.zrevrange(key, start, end)
            return post_ids
        except Exception as e:
            logger.error(f"Failed to get feed from cache: {e}")
            return []

    async def get_feed_count(self, user_id: int) -> int:
        """Get count of items in user's feed"""
        if not self.client:
            return 0

        try:
            key = self._feed_key(user_id)
            count = await self.client.zcard(key)
            return count
        except Exception as e:
            logger.error(f"Failed to get feed count from cache: {e}")
            return 0

    async def clear_feed(self, user_id: int) -> bool:
        """Clear user's feed cache"""
        if not self.client:
            return False

        try:
            key = self._feed_key(user_id)
            await self.client.delete(key)
            return True
        except Exception as e:
            logger.error(f"Failed to clear feed cache: {e}")
            return False

    async def feed_exists(self, user_id: int) -> bool:
        """Check if user's feed exists in cache"""
        if not self.client:
            return False

        try:
            key = self._feed_key(user_id)
            exists = await self.client.exists(key)
            return exists > 0
        except Exception as e:
            logger.error(f"Failed to check feed existence: {e}")
            return False

    async def set_feed_metadata(
        self,
        user_id: int,
        metadata: dict,
        ttl: int = None
    ) -> bool:
        """Set feed metadata"""
        if not self.client:
            return False

        try:
            key = self._feed_metadata_key(user_id)
            await self.client.set(
                key,
                json.dumps(metadata),
                ex=ttl or settings.FEED_CACHE_TTL
            )
            return True
        except Exception as e:
            logger.error(f"Failed to set feed metadata: {e}")
            return False

    async def get_feed_metadata(self, user_id: int) -> Optional[dict]:
        """Get feed metadata"""
        if not self.client:
            return None

        try:
            key = self._feed_metadata_key(user_id)
            data = await self.client.get(key)
            return json.loads(data) if data else None
        except Exception as e:
            logger.error(f"Failed to get feed metadata: {e}")
            return None


# Global cache instance
cache = RedisCache()


async def get_cache() -> RedisCache:
    """Dependency for getting cache instance"""
    return cache
