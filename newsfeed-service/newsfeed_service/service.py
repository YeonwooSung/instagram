"""
Newsfeed Service - Core business logic
"""
from typing import List, Tuple, Optional, Dict, Any
from datetime import datetime
import logging

from .database import Database
from .cache import RedisCache
from .service_client import ServiceClient
from .kafka_producer import KafkaProducerManager
from .config import settings
from .schemas import FeedItemResponse

logger = logging.getLogger(__name__)


class NewsfeedService:
    """Newsfeed service with hybrid fan-out strategy"""

    def __init__(
        self,
        db: Database,
        cache: RedisCache,
        service_client: ServiceClient,
        kafka_producer: KafkaProducerManager
    ):
        self.db = db
        self.cache = cache
        self.service_client = service_client
        self.kafka_producer = kafka_producer

    async def get_user_feed(
        self,
        user_id: int,
        page: int = 1,
        page_size: int = 20,
        token: Optional[str] = None
    ) -> Tuple[List[FeedItemResponse], int, bool]:
        """
        Get user's feed with hybrid strategy

        Returns:
            Tuple of (feed_items, total_count, has_more)
        """
        # Try cache first
        cache_hit = await self._try_get_from_cache(user_id, page, page_size, token)
        if cache_hit:
            logger.info(f"Cache hit for user {user_id}'s feed")
            return cache_hit

        # Check if feed exists in database
        metadata = await self.db.get_feed_metadata(user_id)

        if metadata and not metadata.get("is_stale"):
            # Feed exists and is not stale - get from database
            logger.info(f"Getting feed from database for user {user_id}")
            return await self._get_feed_from_db(user_id, page, page_size, token)

        # Feed doesn't exist or is stale - rebuild it
        logger.info(f"Rebuilding feed for user {user_id}")
        await self._rebuild_user_feed(user_id, token)

        # Get the rebuilt feed
        return await self._get_feed_from_db(user_id, page, page_size, token)

    async def _try_get_from_cache(
        self,
        user_id: int,
        page: int,
        page_size: int,
        token: Optional[str]
    ) -> Optional[Tuple[List[FeedItemResponse], int, bool]]:
        """Try to get feed from Redis cache"""
        if not await self.cache.feed_exists(user_id):
            return None

        start = (page - 1) * page_size
        end = start + page_size - 1

        post_ids = await self.cache.get_feed(user_id, start, end)
        if not post_ids:
            return None

        total_count = await self.cache.get_feed_count(user_id)

        # Fetch post details
        posts = await self.service_client.get_posts_batch(post_ids, token)

        # Convert to response format
        feed_items = []
        for post in posts:
            feed_items.append(FeedItemResponse(
                id=0,  # Not from DB
                post_id=post["id"],
                post_user_id=post["user_id"],
                post_created_at=datetime.fromisoformat(post["created_at"]),
                feed_score=0.0,
                created_at=datetime.utcnow(),
                post_data=post
            ))

        has_more = (start + len(feed_items)) < total_count

        return (feed_items, total_count, has_more)

    async def _get_feed_from_db(
        self,
        user_id: int,
        page: int,
        page_size: int,
        token: Optional[str]
    ) -> Tuple[List[FeedItemResponse], int, bool]:
        """Get feed from database"""
        offset = (page - 1) * page_size

        feed_items_db = await self.db.get_feed_items(user_id, page_size, offset)
        total_count = await self.db.get_feed_count(user_id)

        # Extract post IDs
        post_ids = [item["post_id"] for item in feed_items_db]

        # Fetch post details from post service
        posts = await self.service_client.get_posts_batch(post_ids, token)

        # Create a map for quick lookup
        posts_map = {post["id"]: post for post in posts}

        # Build response
        feed_items = []
        for item in feed_items_db:
            post_data = posts_map.get(item["post_id"])
            feed_items.append(FeedItemResponse(
                id=item["id"],
                post_id=item["post_id"],
                post_user_id=item["post_user_id"],
                post_created_at=item["post_created_at"],
                feed_score=item.get("feed_score", 0.0),
                created_at=item["created_at"],
                post_data=post_data
            ))

        # Update cache asynchronously (don't wait)
        if feed_items:
            cache_items = [
                (item["post_id"], item["post_created_at"].timestamp())
                for item in feed_items_db
            ]
            await self.cache.add_to_feed_bulk(user_id, cache_items)

        has_more = (offset + len(feed_items)) < total_count

        return (feed_items, total_count, has_more)

    async def _rebuild_user_feed(self, user_id: int, token: Optional[str]):
        """Rebuild user's feed from scratch"""
        logger.info(f"Rebuilding feed for user {user_id}")

        try:
            # Get list of users the user is following
            following_ids = await self.service_client.get_following_ids(user_id, token)

            if not following_ids:
                logger.info(f"User {user_id} is not following anyone")
                await self.db.update_feed_metadata(user_id, 0, False)
                return

            # Fetch recent posts from all followed users
            all_posts = []
            for following_id in following_ids[:100]:  # Limit to prevent overload
                posts = await self.service_client.get_user_posts(
                    following_id,
                    token,
                    limit=10  # Last 10 posts per user
                )
                all_posts.extend(posts)

            if not all_posts:
                logger.info(f"No posts found for user {user_id}'s feed")
                await self.db.update_feed_metadata(user_id, 0, False)
                return

            # Sort by created_at (newest first)
            all_posts.sort(key=lambda p: p.get("created_at", ""), reverse=True)

            # Limit to max feed items
            all_posts = all_posts[:settings.MAX_FEED_ITEMS_PER_USER]

            # Prepare bulk insert data
            feed_items = []
            for post in all_posts:
                created_at = datetime.fromisoformat(post["created_at"])
                feed_items.append((
                    user_id,
                    post["id"],
                    post["user_id"],
                    created_at,
                    0.0  # feed_score
                ))

            # Bulk insert into database
            await self.db.add_feed_items_bulk(feed_items)

            # Update metadata
            await self.db.update_feed_metadata(user_id, len(feed_items), False)

            # Update cache
            cache_items = [
                (post["id"], datetime.fromisoformat(post["created_at"]).timestamp())
                for post in all_posts
            ]
            await self.cache.add_to_feed_bulk(user_id, cache_items)

            logger.info(f"Rebuilt feed for user {user_id} with {len(feed_items)} items")

        except Exception as e:
            logger.error(f"Error rebuilding feed for user {user_id}: {e}")
            raise

    async def add_post_to_followers_feeds(
        self,
        post_id: str,
        post_user_id: int,
        post_created_at: datetime,
        token: str
    ) -> int:
        """
        Fan-out: Add post to all followers' feeds (for non-celebrities)

        Returns:
            Number of feeds updated
        """
        try:
            # Check if user is a celebrity
            follower_count = await self.service_client.get_follower_count(
                post_user_id,
                token
            )

            if follower_count > settings.CELEBRITY_FOLLOWER_THRESHOLD:
                logger.info(
                    f"User {post_user_id} is a celebrity ({follower_count} followers) "
                    f"- skipping fan-out on write"
                )
                return 0

            # Get followers
            follower_ids = await self.service_client.get_followers_ids(
                post_user_id,
                token
            )

            if not follower_ids:
                logger.info(f"User {post_user_id} has no followers")
                return 0

            # Prepare bulk insert
            timestamp = post_created_at.timestamp()
            feed_items = []
            cache_updates = []

            for follower_id in follower_ids:
                feed_items.append((
                    follower_id,
                    post_id,
                    post_user_id,
                    post_created_at,
                    0.0  # feed_score
                ))
                cache_updates.append((follower_id, post_id, timestamp))

            # Bulk insert into database
            inserted = await self.db.add_feed_items_bulk(feed_items)

            # Update cache for each follower
            for follower_id, post_id_val, ts in cache_updates:
                await self.cache.add_to_feed(follower_id, post_id_val, ts)

            logger.info(f"Added post {post_id} to {inserted} followers' feeds")
            return inserted

        except Exception as e:
            logger.error(f"Error adding post to followers' feeds: {e}")
            return 0

    async def remove_post_from_all_feeds(self, post_id: str) -> int:
        """
        Remove post from all feeds

        Returns:
            Number of feeds updated
        """
        count = await self.db.remove_feed_items_by_post(post_id)
        logger.info(f"Removed post {post_id} from {count} feeds")
        return count

    async def get_feed_stats(self, user_id: int) -> Dict[str, Any]:
        """Get feed statistics for user"""
        metadata = await self.db.get_feed_metadata(user_id)

        if not metadata:
            return {
                "user_id": user_id,
                "total_items": 0,
                "last_updated": None,
                "cache_status": "miss"
            }

        cache_exists = await self.cache.feed_exists(user_id)

        return {
            "user_id": user_id,
            "total_items": metadata.get("total_items", 0),
            "last_updated": metadata.get("last_updated"),
            "cache_status": "hit" if cache_exists else "miss"
        }

    async def refresh_user_feed(self, user_id: int, token: str) -> bool:
        """Manually refresh user's feed"""
        try:
            # Mark as stale
            await self.db.mark_feed_stale(user_id)

            # Clear cache
            await self.cache.clear_feed(user_id)

            # Rebuild
            await self._rebuild_user_feed(user_id, token)

            return True
        except Exception as e:
            logger.error(f"Error refreshing feed for user {user_id}: {e}")
            return False
