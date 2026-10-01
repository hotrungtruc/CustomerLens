"""
Messaging package — centralized Kafka/Redpanda and Redis connection and lifecycle management.
"""

from app.messaging.kafka_client import (
    KAFKA_BOOTSTRAP_SERVERS,
    REDIS_URL,
    KAFKA_CAMERA_FRAMES_TOPIC,
    REDIS_CAMERA_FRAMES_FALLBACK_QUEUE,
    init_kafka_producer,
    close_kafka_producer,
    send_camera_frame,
    get_redis,
    init_topics,
)

__all__ = [
    "KAFKA_BOOTSTRAP_SERVERS",
    "REDIS_URL",
    "KAFKA_CAMERA_FRAMES_TOPIC",
    "REDIS_CAMERA_FRAMES_FALLBACK_QUEUE",
    "init_kafka_producer",
    "close_kafka_producer",
    "send_camera_frame",
    "get_redis",
    "init_topics",
]
