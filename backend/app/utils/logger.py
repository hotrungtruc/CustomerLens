"""
Centralized logging configuration for the Face Recognition backend.

Usage:
    from app.utils.logger import get_logger
    logger = get_logger(__name__)
    logger.info("Model loaded: %s", model_name)
"""

import logging
import sys


def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """Return a named logger with a consistent format.

    All loggers share the same StreamHandler so output is uniform.
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(
            logging.Formatter(
                "[%(asctime)s] %(levelname)s %(name)s: %(message)s",
                datefmt="%H:%M:%S",
            )
        )
        logger.addHandler(handler)
    logger.setLevel(level)
    return logger
