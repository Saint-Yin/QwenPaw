"""Centralized logging configuration for the backend."""

import logging
import sys
import os


def setup_logger(name: str = "app", logging_level: str = "INFO") -> logging.Logger:
    """Create and configure a logger instance.

    Args:
        name: Logger name, typically module or component name.

    Returns:
        Configured logger instance.
    """
    _logger = logging.getLogger(name)

    # Avoid adding duplicate handlers if called multiple times
    if _logger.handlers:
        return _logger

    # Override logging level set by code.
    env_logging_level = os.environ.get('CREATOR_LOGGING_LEVEL', '').upper()
    if env_logging_level:
        logging_level = env_logging_level

    _logger.setLevel(logging_level)

    # Console handler with formatted output
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging_level)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(filename)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    _logger.addHandler(handler)

    # Prevent propagation to root logger to avoid duplicate messages
    _logger.propagate = False

    return _logger


# Default application logger
logger = setup_logger()
