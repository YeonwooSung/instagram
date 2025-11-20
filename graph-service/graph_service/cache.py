"""
Redis caching layer for Graph Service
"""
import redis.asyncio as redis
from typing import Optional, List, Any
import json
import logging

from .config import settings

logger = logging.getLogger(__name__)


class RedisCache:
    """Redis cache manager for graph relationships"""

    def __init__(self):
        self.redis: Optional[redis.Redis] = None

    async def connect(self):
        """Connect to Redis"""
        if not settings.REDIS_ENABLED:
            logger.info("Redis caching is disabled")
            return

        try:
            self.redis = await redis.from_url(
                f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}",
                password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
                encoding="utf-8",
                decode_responses=True,
            )
            # Test connection
            await self.redis.ping()
            logger.info("Connected to Redis successfully")
        except Exception as e:
            logger.warning(f"Failed to connect to Redis: {e}. Continuing without cache.")
            self.redis = None

    async def disconnect(self):
        """Disconnect from Redis"""
        if self.redis:
            await self.redis.close()
            logger.info("Disconnected from Redis")

    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        if not self.redis:
            return None

        try:
            value = await self.redis.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.error(f"Error getting cache key {key}: {e}")
            return None

    async def set(self, key: str, value: Any, ttl: int = 300):
        """Set value in cache with TTL"""
        if not self.redis:
            return

        try:
            await self.redis.setex(key, ttl, json.dumps(value))
        except Exception as e:
            logger.error(f"Error setting cache key {key}: {e}")

    async def delete(self, key: str):
        """Delete key from cache"""
        if not self.redis:
            return

        try:
            await self.redis.delete(key)
        except Exception as e:
            logger.error(f"Error deleting cache key {key}: {e}")

    async def delete_pattern(self, pattern: str):
        """Delete all keys matching pattern"""
        if not self.redis:
            return

        try:
            keys = []
            async for key in self.redis.scan_iter(match=pattern):
                keys.append(key)

            if keys:
                await self.redis.delete(*keys)
                logger.info(f"Deleted {len(keys)} keys matching pattern {pattern}")
        except Exception as e:
            logger.error(f"Error deleting cache pattern {pattern}: {e}")

    # Graph-specific cache methods
    def _followers_key(self, user_id: int) -> str:
        """Generate cache key for followers list"""
        return f"graph:followers:{user_id}"

    def _following_key(self, user_id: int) -> str:
        """Generate cache key for following list"""
        return f"graph:following:{user_id}"

    def _relationship_key(self, user_id: int, other_user_id: int) -> str:
        """Generate cache key for relationship"""
        return f"graph:relationship:{user_id}:{other_user_id}"

    def _stats_key(self, user_id: int) -> str:
        """Generate cache key for user stats"""
        return f"graph:stats:{user_id}"

    async def get_followers(self, user_id: int) -> Optional[List[dict]]:
        """Get cached followers list"""
        return await self.get(self._followers_key(user_id))

    async def set_followers(self, user_id: int, followers: List[dict]):
        """Cache followers list"""
        await self.set(
            self._followers_key(user_id), followers, settings.CACHE_TTL_FOLLOWERS
        )

    async def get_following(self, user_id: int) -> Optional[List[dict]]:
        """Get cached following list"""
        return await self.get(self._following_key(user_id))

    async def set_following(self, user_id: int, following: List[dict]):
        """Cache following list"""
        await self.set(
            self._following_key(user_id), following, settings.CACHE_TTL_FOLLOWING
        )

    async def get_relationship(
        self, user_id: int, other_user_id: int
    ) -> Optional[dict]:
        """Get cached relationship"""
        return await self.get(self._relationship_key(user_id, other_user_id))

    async def set_relationship(self, user_id: int, other_user_id: int, relationship: dict):
        """Cache relationship"""
        await self.set(
            self._relationship_key(user_id, other_user_id),
            relationship,
            settings.CACHE_TTL_RELATIONSHIP,
        )

    async def get_stats(self, user_id: int) -> Optional[dict]:
        """Get cached user stats"""
        return await self.get(self._stats_key(user_id))

    async def set_stats(self, user_id: int, stats: dict):
        """Cache user stats"""
        await self.set(self._stats_key(user_id), stats, settings.CACHE_TTL_STATS)

    async def invalidate_user_cache(self, user_id: int):
        """Invalidate all cache for a user"""
        await self.delete(self._followers_key(user_id))
        await self.delete(self._following_key(user_id))
        await self.delete(self._stats_key(user_id))
        # Also invalidate relationships
        await self.delete_pattern(f"graph:relationship:{user_id}:*")
        await self.delete_pattern(f"graph:relationship:*:{user_id}")

    async def invalidate_relationship_cache(self, user_id: int, other_user_id: int):
        """Invalidate relationship cache between two users"""
        await self.delete(self._relationship_key(user_id, other_user_id))
        await self.delete(self._relationship_key(other_user_id, user_id))


# Global cache instance
cache = RedisCache()


async def get_cache() -> RedisCache:
    """Dependency for getting cache instance"""
    return cache
