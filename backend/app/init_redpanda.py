"""
Init script for Redpanda/Kafka topics.
Delegates to app.messaging.kafka_client for single source of truth.
"""

import logging
from app.messaging.kafka_client import init_topics, KAFKA_BOOTSTRAP_SERVERS

logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    init_topics()
