import os
from kafka.admin import KafkaAdminClient, NewTopic
from kafka.errors import TopicAlreadyExistsError
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "redpanda:9092")

def init_topics():
    logger.info(f"Connecting to Kafka admin client at {KAFKA_BOOTSTRAP_SERVERS}...")
    try:
        admin_client = KafkaAdminClient(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            client_id='init_script'
        )
        
        # Topic configs: retention.bytes = 2GB = 2147483648
        topic_list = [
            NewTopic(
                name="camera_frames", 
                num_partitions=3, 
                replication_factor=1, 
                topic_configs={'retention.bytes': '2147483648'}
            )
        ]
        
        try:
            admin_client.create_topics(new_topics=topic_list, validate_only=False)
            logger.info("Topic 'camera_frames' created successfully with 2GB retention.")
        except TopicAlreadyExistsError:
            logger.info("Topic 'camera_frames' already exists.")
            
    except Exception as e:
        logger.error(f"Failed to initialize Redpanda topic: {e}")

if __name__ == "__main__":
    init_topics()
