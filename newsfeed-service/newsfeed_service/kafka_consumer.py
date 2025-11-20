"""
Kafka consumer for processing events from other services
"""
from aiokafka import AIOKafkaConsumer
from typing import Optional
import json
import asyncio
import logging
from datetime import datetime

from .config import settings
from .database import db
from .cache import cache
from .service_client import service_client

logger = logging.getLogger(__name__)


class KafkaConsumerManager:
    """Manage Kafka consumer for event processing"""

    def __init__(self):
        self.consumer: Optional[AIOKafkaConsumer] = None
        self.running = False
        self.task: Optional[asyncio.Task] = None

    async def start(self):
        """Start Kafka consumer"""
        if not settings.KAFKA_ENABLED:
            logger.warning("Kafka is disabled")
            return

        try:
            self.consumer = AIOKafkaConsumer(
                settings.KAFKA_TOPIC_POST_CREATED,
                settings.KAFKA_TOPIC_POST_DELETED,
                settings.KAFKA_TOPIC_FOLLOW_ACCEPTED,
                settings.KAFKA_TOPIC_UNFOLLOW,
                bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
                group_id=settings.KAFKA_CONSUMER_GROUP,
                value_deserializer=lambda m: json.loads(m.decode('utf-8')),
                auto_offset_reset='latest',  # Start from latest messages
                enable_auto_commit=True,
            )
            await self.consumer.start()
            logger.info(f"Kafka consumer started with group '{settings.KAFKA_CONSUMER_GROUP}'")

            # Start consuming messages in background
            self.running = True
            self.task = asyncio.create_task(self._consume_messages())

        except Exception as e:
            logger.error(f"Failed to start Kafka consumer: {e}")
            self.consumer = None

    async def stop(self):
        """Stop Kafka consumer"""
        self.running = False

        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

        if self.consumer:
            await self.consumer.stop()
            logger.info("Kafka consumer stopped")

    async def _consume_messages(self):
        """Consume and process messages from Kafka"""
        logger.info("Started consuming Kafka messages")

        try:
            async for message in self.consumer:
                if not self.running:
                    break

                try:
                    await self._process_message(message)
                except Exception as e:
                    logger.error(f"Error processing message: {e}")

        except asyncio.CancelledError:
            logger.info("Kafka consumer task cancelled")
        except Exception as e:
            logger.error(f"Error in message consumption loop: {e}")

    async def _process_message(self, message):
        """Process individual Kafka message"""
        topic = message.topic
        value = message.value

        logger.info(f"Processing message from topic '{topic}': {value.get('event_type')}")

        try:
            if topic == settings.KAFKA_TOPIC_POST_CREATED:
                await self._handle_post_created(value)
            elif topic == settings.KAFKA_TOPIC_POST_DELETED:
                await self._handle_post_deleted(value)
            elif topic == settings.KAFKA_TOPIC_FOLLOW_ACCEPTED:
                await self._handle_follow_accepted(value)
            elif topic == settings.KAFKA_TOPIC_UNFOLLOW:
                await self._handle_unfollow(value)
            else:
                logger.warning(f"Unknown topic: {topic}")

        except Exception as e:
            logger.error(f"Failed to handle message from topic '{topic}': {e}")

    async def _handle_post_created(self, event: dict):
        """
        Handle post created event - Fan out to followers' feeds

        Event format:
        {
            "event_type": "post_created",
            "post_id": "...",
            "user_id": 123,
            "post_data": {...}
        }
        """
        post_id = event.get("post_id")
        user_id = event.get("user_id")
        post_data = event.get("post_data", {})
        created_at_str = event.get("timestamp") or post_data.get("created_at")

        if not post_id or not user_id:
            logger.error("Invalid post_created event: missing post_id or user_id")
            return

        logger.info(f"Handling post_created: post_id={post_id}, user_id={user_id}")

        try:
            # Parse timestamp
            if isinstance(created_at_str, str):
                created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
            else:
                created_at = datetime.utcnow()

            timestamp_score = created_at.timestamp()

            # Check if user is a celebrity (has many followers)
            # We need a token to call graph service - skip for now in consumer
            # In production, use service-to-service authentication

            # For now, use fan-out on write for all users
            # Get followers from graph service
            # Since we don't have auth token here, we'll do a simpler approach:
            # Just log the event. Actual fan-out will happen on-demand when users request their feed.

            logger.info(f"Post {post_id} created by user {user_id} - feed will be updated on-demand")

            # Alternative: Store in a pending queue and process with a background worker
            # that has proper service credentials

        except Exception as e:
            logger.error(f"Error handling post_created event: {e}")

    async def _handle_post_deleted(self, event: dict):
        """
        Handle post deleted event - Remove from all feeds

        Event format:
        {
            "event_type": "post_deleted",
            "post_id": "...",
            "user_id": 123
        }
        """
        post_id = event.get("post_id")
        user_id = event.get("user_id")

        if not post_id:
            logger.error("Invalid post_deleted event: missing post_id")
            return

        logger.info(f"Handling post_deleted: post_id={post_id}")

        try:
            # Remove from database
            count = await db.remove_feed_items_by_post(post_id)
            logger.info(f"Removed post {post_id} from {count} feeds")

            # Note: Redis cache will auto-expire or be invalidated on next read

        except Exception as e:
            logger.error(f"Error handling post_deleted event: {e}")

    async def _handle_follow_accepted(self, event: dict):
        """
        Handle follow accepted event - Add followee's posts to follower's feed

        Event format:
        {
            "event_type": "follow_accepted",
            "follower_id": 123,
            "following_id": 456,
            "timestamp": "..."
        }
        """
        follower_id = event.get("follower_id")
        following_id = event.get("following_id")

        if not follower_id or not following_id:
            logger.error("Invalid follow_accepted event: missing user IDs")
            return

        logger.info(f"Handling follow_accepted: follower={follower_id}, following={following_id}")

        try:
            # Mark follower's feed as stale - will be rebuilt on next request
            await db.mark_feed_stale(follower_id)

            # Clear Redis cache
            await cache.clear_feed(follower_id)

            logger.info(f"Marked feed as stale for user {follower_id}")

        except Exception as e:
            logger.error(f"Error handling follow_accepted event: {e}")

    async def _handle_unfollow(self, event: dict):
        """
        Handle unfollow event - Remove unfollowed user's posts from feed

        Event format:
        {
            "event_type": "unfollow",
            "follower_id": 123,
            "following_id": 456
        }
        """
        follower_id = event.get("follower_id")
        following_id = event.get("following_id")

        if not follower_id or not following_id:
            logger.error("Invalid unfollow event: missing user IDs")
            return

        logger.info(f"Handling unfollow: follower={follower_id}, following={following_id}")

        try:
            # Remove all posts from the unfollowed user
            count = await db.remove_feed_items_by_author(follower_id, following_id)
            logger.info(f"Removed {count} posts from user {follower_id}'s feed")

            # Clear Redis cache
            await cache.clear_feed(follower_id)

        except Exception as e:
            logger.error(f"Error handling unfollow event: {e}")


# Global Kafka consumer instance
kafka_consumer = KafkaConsumerManager()
