import os
import json
import uuid
import asyncio
import logging
from aiokafka import AIOKafkaProducer, AIOKafkaConsumer

logger = logging.getLogger("KafkaManager")

KAFKA_BROKER_URL = os.getenv("KAFKA_BROKER_URL", "redpanda:29092")
GATEWAY_UUID = uuid.uuid4().hex

# Dictionary to route messages from Kafka to the correct WebSocket handler
WEBSOCKET_QUEUES = {}

kafka_producer = None
kafka_consumer = None
consumer_task = None

async def init_kafka():
    global kafka_producer, kafka_consumer, consumer_task
    
    logger.info(f"Initializing Kafka with broker {KAFKA_BROKER_URL} and Gateway UUID {GATEWAY_UUID}")
    try:
        kafka_producer = AIOKafkaProducer(
            bootstrap_servers=KAFKA_BROKER_URL,
            value_serializer=lambda v: v if isinstance(v, bytes) else json.dumps(v).encode('utf-8')
        )
        await kafka_producer.start()
        
        reply_topic = f"results_gateway_{GATEWAY_UUID}"
        kafka_consumer = AIOKafkaConsumer(
            reply_topic,
            bootstrap_servers=KAFKA_BROKER_URL,
            group_id=f"gateway_{GATEWAY_UUID}",
            auto_offset_reset='latest',
            value_deserializer=lambda m: json.loads(m.decode('utf-8'))
        )
        await kafka_consumer.start()
        
        consumer_task = asyncio.create_task(consume_kafka_messages())
        logger.info("Kafka initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize Kafka: {e}")

async def close_kafka():
    if consumer_task:
        consumer_task.cancel()
    if kafka_consumer:
        await kafka_consumer.stop()
    if kafka_producer:
        await kafka_producer.stop()

async def consume_kafka_messages():
    try:
        async for msg in kafka_consumer:
            data = msg.value
            connection_id = data.get("connection_id")
            if connection_id and connection_id in WEBSOCKET_QUEUES:
                await WEBSOCKET_QUEUES[connection_id].put(data)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Kafka consumer error: {e}")

async def send_frame(camera_id: str, packed_payload: bytes):
    if kafka_producer:
        await kafka_producer.send_and_wait(
            "camera_frames_v2", 
            key=camera_id.encode('utf-8'),
            value=packed_payload
        )
