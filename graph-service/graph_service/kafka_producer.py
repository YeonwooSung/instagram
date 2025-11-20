"""
Kafka producer for publishing graph events
"""
from aiokafka import AIOKafkaProducer
from typing import Optional, Dict, Any
import json
import logging
from datetime import datetime

from .config import settings

logger = logging.getLogger(__name__)


class KafkaProducerManager:
    """Kafka producer manager for publishing events"""

    def __init__(self):
        self.producer: Optional[AIOKafkaProducer] = None

    async def start(self):
        """Start Kafka producer"""
        if not settings.KAFKA_ENABLED:
            logger.info("Kafka is disabled")
            return

        try:
            self.producer = AIOKafkaProducer(
                bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                key_serializer=lambda v: str(v).encode("utf-8") if v else None,
            )
            await self.producer.start()
            logger.info("Kafka producer started successfully")
        except Exception as e:
            logger.warning(f"Failed to start Kafka producer: {e}. Continuing without Kafka.")
            self.producer = None

    async def stop(self):
        """Stop Kafka producer"""
        if self.producer:
            await self.producer.stop()
            logger.info("Kafka producer stopped")

    async def publish_event(self, topic: str, key: str, event_data: Dict[str, Any]):
        """
        Publish event to Kafka topic

        Args:
            topic: Kafka topic name
            key: Message key (usually user_id)
            event_data: Event data to publish
        """
        if not self.producer:
            logger.debug(f"Kafka disabled, skipping event: {topic}")
            return

        try:
            await self.producer.send(topic, value=event_data, key=key)
            logger.info(f"Published event to {topic}: {key}")
        except Exception as e:
            logger.error(f"Error publishing event to {topic}: {e}")

    # Graph-specific event publishers
    async def publish_follow_event(
        self, follower_id: int, following_id: int, status: str
    ):
        """Publish follow event"""
        event_data = {
            "event_type": "follow",
            "follower_id": follower_id,
            "following_id": following_id,
            "status": status,
            "timestamp": datetime.utcnow().isoformat(),
        }
        await self.publish_event("graph.follow", str(follower_id), event_data)

    async def publish_unfollow_event(self, follower_id: int, following_id: int):
        """Publish unfollow event"""
        event_data = {
            "event_type": "unfollow",
            "follower_id": follower_id,
            "following_id": following_id,
            "timestamp": datetime.utcnow().isoformat(),
        }
        await self.publish_event(settings.KAFKA_TOPIC_FOLLOW_REMOVED, str(follower_id), event_data)

    async def publish_follow_request_accepted_event(
        self, follower_id: int, following_id: int
    ):
        """Publish follow request accepted event"""
        event_data = {
            "event_type": "follow_accepted",
            "follower_id": follower_id,
            "following_id": following_id,
            "timestamp": datetime.utcnow().isoformat(),
        }
        await self.publish_event(settings.KAFKA_TOPIC_FOLLOW_ACCEPTED, str(follower_id), event_data)

    async def publish_follow_request_rejected_event(
        self, follower_id: int, following_id: int
    ):
        """Publish follow request rejected event"""
        event_data = {
            "event_type": "follow_request_rejected",
            "follower_id": follower_id,
            "following_id": following_id,
            "timestamp": datetime.utcnow().isoformat(),
        }
        await self.publish_event("graph.follow_rejected", str(follower_id), event_data)


# Global producer instance
kafka_producer = KafkaProducerManager()


async def get_kafka_producer() -> KafkaProducerManager:
    """Dependency for getting Kafka producer instance"""
    return kafka_producer
