"""
Kafka producer for publishing feed events
"""
from aiokafka import AIOKafkaProducer
from typing import Optional, Dict, Any
import json
import logging

from .config import settings

logger = logging.getLogger(__name__)


class KafkaProducerManager:
    """Manage Kafka producer for event publishing"""

    def __init__(self):
        self.producer: Optional[AIOKafkaProducer] = None

    async def start(self):
        """Start Kafka producer"""
        if not settings.KAFKA_ENABLED:
            logger.warning("Kafka is disabled")
            return

        try:
            self.producer = AIOKafkaProducer(
                bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                key_serializer=lambda k: k.encode('utf-8') if k else None,
            )
            await self.producer.start()
            logger.info(f"Kafka producer started at {settings.KAFKA_BOOTSTRAP_SERVERS}")
        except Exception as e:
            logger.error(f"Failed to start Kafka producer: {e}")
            self.producer = None

    async def stop(self):
        """Stop Kafka producer"""
        if self.producer:
            await self.producer.stop()
            logger.info("Kafka producer stopped")

    async def publish_event(
        self,
        topic: str,
        key: str,
        event_data: Dict[str, Any]
    ) -> bool:
        """
        Publish an event to Kafka

        Args:
            topic: Kafka topic name
            key: Message key
            event_data: Event payload

        Returns:
            True if successful, False otherwise
        """
        if not self.producer:
            logger.warning("Kafka producer not available, skipping event publishing")
            return False

        try:
            await self.producer.send(topic, value=event_data, key=key)
            logger.debug(f"Published event to topic '{topic}' with key '{key}'")
            return True
        except Exception as e:
            logger.error(f"Failed to publish event to topic '{topic}': {e}")
            return False

    async def publish_feed_updated(
        self,
        user_id: int,
        post_id: str,
        action: str
    ) -> bool:
        """
        Publish feed updated event

        Args:
            user_id: User whose feed was updated
            post_id: Post ID that was added/removed
            action: 'added' or 'removed'
        """
        event = {
            "event_type": "feed_updated",
            "user_id": user_id,
            "post_id": post_id,
            "action": action,
        }
        return await self.publish_event(
            settings.KAFKA_TOPIC_FEED_UPDATED,
            str(user_id),
            event
        )


# Global Kafka producer instance
kafka_producer = KafkaProducerManager()


async def get_kafka_producer() -> KafkaProducerManager:
    """Dependency for getting Kafka producer instance"""
    return kafka_producer
