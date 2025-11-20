"""
Kafka producer for publishing post events
"""
from aiokafka import AIOKafkaProducer
from typing import Optional, Dict, Any
import json
from config import settings
import logging

logger = logging.getLogger(__name__)


class KafkaProducerManager:
    """Manage Kafka producer for event publishing"""

    def __init__(self):
        self.producer: Optional[AIOKafkaProducer] = None

    async def start(self):
        """Start Kafka producer"""
        try:
            self.producer = AIOKafkaProducer(
                bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                key_serializer=lambda k: k.encode('utf-8') if k else None,
            )
            await self.producer.start()
            print(f"✓ Kafka producer started at {settings.KAFKA_BOOTSTRAP_SERVERS}")
        except Exception as e:
            logger.error(f"Failed to start Kafka producer: {e}")
            print(f"⚠ Kafka producer not available: {e}")

    async def stop(self):
        """Stop Kafka producer"""
        if self.producer:
            await self.producer.stop()
            print("✓ Kafka producer stopped")

    async def publish_event(self, topic: str, key: str, event_data: Dict[str, Any]) -> bool:
        """
        Publish an event to Kafka

        Args:
            topic: Kafka topic name
            key: Message key (usually user_id or post_id)
            event_data: Event payload

        Returns:
            True if successful, False otherwise
        """
        if not self.producer:
            logger.warning("Kafka producer not available, skipping event publishing")
            return False

        try:
            await self.producer.send(topic, value=event_data, key=key)
            logger.info(f"Published event to topic '{topic}' with key '{key}'")
            return True
        except Exception as e:
            logger.error(f"Failed to publish event to topic '{topic}': {e}")
            return False

    async def publish_post_created(self, post_id: str, user_id: int, post_data: Dict[str, Any]) -> bool:
        """Publish post created event"""
        event = {
            "event_type": "post_created",
            "post_id": post_id,
            "user_id": user_id,
            "post_data": post_data,
            "timestamp": post_data.get("created_at")
        }
        return await self.publish_event(
            settings.KAFKA_TOPIC_POST_CREATED,
            str(post_id),
            event
        )

    async def publish_post_updated(self, post_id: str, user_id: int, post_data: Dict[str, Any]) -> bool:
        """Publish post updated event"""
        event = {
            "event_type": "post_updated",
            "post_id": post_id,
            "user_id": user_id,
            "post_data": post_data,
            "timestamp": post_data.get("updated_at")
        }
        return await self.publish_event(
            settings.KAFKA_TOPIC_POST_UPDATED,
            str(post_id),
            event
        )

    async def publish_post_deleted(self, post_id: str, user_id: int) -> bool:
        """Publish post deleted event"""
        event = {
            "event_type": "post_deleted",
            "post_id": post_id,
            "user_id": user_id,
        }
        return await self.publish_event(
            settings.KAFKA_TOPIC_POST_DELETED,
            str(post_id),
            event
        )

    async def publish_post_liked(self, post_id: str, user_id: int, liker_user_id: int) -> bool:
        """Publish post liked event"""
        event = {
            "event_type": "post_liked",
            "post_id": post_id,
            "post_owner_id": user_id,
            "liker_user_id": liker_user_id,
        }
        return await self.publish_event(
            settings.KAFKA_TOPIC_POST_LIKED,
            str(post_id),
            event
        )

    async def publish_post_commented(self, post_id: str, user_id: int, commenter_user_id: int, comment_id: str) -> bool:
        """Publish post commented event"""
        event = {
            "event_type": "post_commented",
            "post_id": post_id,
            "post_owner_id": user_id,
            "commenter_user_id": commenter_user_id,
            "comment_id": comment_id,
        }
        return await self.publish_event(
            settings.KAFKA_TOPIC_POST_COMMENTED,
            str(post_id),
            event
        )


# Global Kafka producer instance
kafka_producer = KafkaProducerManager()
