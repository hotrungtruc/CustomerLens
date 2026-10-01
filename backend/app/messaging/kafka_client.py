"""
Kafka/Redpanda client with automatic Redis fallback.
Centralises all messaging setup so routes and workers don't duplicate connection logic.
"""

import asyncio
import logging
import os

import redis.asyncio as aioredis
from aiokafka import AIOKafkaProducer

from config import (
    KAFKA_BOOTSTRAP_SERVERS,
    REDIS_URL,
    KAFKA_CAMERA_FRAMES_TOPIC,
    REDIS_CAMERA_FRAMES_FALLBACK_QUEUE,
)

logger = logging.getLogger("KafkaClient")

# ---------------------------------------------------------------------------
# Kafka producer (module-level singleton)
# ---------------------------------------------------------------------------
kafka_producer: AIOKafkaProducer = None
_reconnect_task: asyncio.Task = None

# ---------------------------------------------------------------------------
# Redis connection pool (module-level singleton)
# ---------------------------------------------------------------------------
redis_pool = aioredis.ConnectionPool.from_url(REDIS_URL, max_connections=200)


async def get_redis() -> aioredis.Redis:
    return aioredis.Redis(connection_pool=redis_pool)


# ---------------------------------------------------------------------------
# Topic Initialization (Admin)
# ---------------------------------------------------------------------------

def init_topics():
    """
    Initializes required topics (e.g. camera_frames) in Redpanda / Kafka.
    Can be invoked synchronously or via asyncio.to_thread.
    """
    try:
        from kafka.admin import KafkaAdminClient, NewTopic
        from kafka.errors import TopicAlreadyExistsError
    except ImportError:
        logger.warning("kafka-python not installed; skipping admin topic init.")
        return

    logger.info(f"Connecting to Kafka admin client at {KAFKA_BOOTSTRAP_SERVERS}...")
    try:
        admin_client = KafkaAdminClient(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            client_id="init_script",
        )
        topic_list = [
            NewTopic(
                name=KAFKA_CAMERA_FRAMES_TOPIC,
                num_partitions=3,
                replication_factor=1,
                topic_configs={"retention.bytes": "2147483648"},  # 2GB retention
            )
        ]
        try:
            admin_client.create_topics(new_topics=topic_list, validate_only=False)
            logger.info(f"Topic '{KAFKA_CAMERA_FRAMES_TOPIC}' created successfully with 2GB retention.")
        except TopicAlreadyExistsError:
            logger.info(f"Topic '{KAFKA_CAMERA_FRAMES_TOPIC}' already exists.")
        finally:
            admin_client.close()
    except Exception as e:
        logger.error(f"Failed to initialize Redpanda topic: {e}")


# ---------------------------------------------------------------------------
# Kafka lifecycle
# ---------------------------------------------------------------------------

async def _kafka_reconnect_loop():
    global kafka_producer
    while True:
        await asyncio.sleep(5)
        if kafka_producer is not None:
            break
        try:
            print(
                f"[RETRY] Attempting to reconnect to Redpanda at {KAFKA_BOOTSTRAP_SERVERS}...",
                flush=True,
            )
            producer = AIOKafkaProducer(bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS)
            await producer.start()
            kafka_producer = producer
            print(
                f"[SUCCESS] Reconnected to Redpanda at {KAFKA_BOOTSTRAP_SERVERS}!",
                flush=True,
            )
            break
        except Exception as e:
            print(f"[RETRY FAILED] Redpanda unavailable: {e}", flush=True)


def _trigger_kafka_reconnect():
    global _reconnect_task, kafka_producer
    kafka_producer = None
    if _reconnect_task is None or _reconnect_task.done():
        try:
            loop = asyncio.get_running_loop()
            _reconnect_task = loop.create_task(_kafka_reconnect_loop())
        except RuntimeError:
            pass


async def init_kafka_producer():
    global kafka_producer
    try:
        await asyncio.to_thread(init_topics)
    except Exception as e:
        print(f"Failed to auto-init Redpanda topic: {e}", flush=True)

    try:
        kafka_producer = AIOKafkaProducer(bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS)
        await kafka_producer.start()
        print(f"Connected to Redpanda at {KAFKA_BOOTSTRAP_SERVERS}", flush=True)
    except Exception as e:
        print(
            f"Failed to connect to Redpanda ({e}). Launching background auto-reconnect...",
            flush=True,
        )
        _trigger_kafka_reconnect()


async def close_kafka_producer():
    global kafka_producer, _reconnect_task
    if _reconnect_task and not _reconnect_task.done():
        _reconnect_task.cancel()
    if kafka_producer:
        await kafka_producer.stop()
        kafka_producer = None


# ---------------------------------------------------------------------------
# Frame publishing (Kafka primary, Redis fallback)
# ---------------------------------------------------------------------------

async def send_camera_frame(redis_conn, packed_payload: bytes, camera_id: str):
    """
    Publishes a camera frame to Redpanda.
    Falls back to Redis queue when Redpanda is down.
    """
    global kafka_producer
    sent_via_kafka = False
    if kafka_producer is not None:
        try:
            await kafka_producer.send_and_wait(KAFKA_CAMERA_FRAMES_TOPIC, packed_payload)
            sent_via_kafka = True
        except Exception as e:
            print(
                f"[FALLBACK WARNING] Redpanda send error ({e}). Switching to Redis queue fallback.",
                flush=True,
            )
            _trigger_kafka_reconnect()

    if not sent_via_kafka:
        try:
            await redis_conn.lpush(REDIS_CAMERA_FRAMES_FALLBACK_QUEUE, packed_payload)
            await redis_conn.ltrim(REDIS_CAMERA_FRAMES_FALLBACK_QUEUE, 0, 50)
        except Exception as e:
            print(f"[ERROR] Redis fallback frame push error: {e}", flush=True)
