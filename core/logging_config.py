# src/core/logging_config.py
import logging

LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOGGER_NAME = "aina"


def setup_logger() -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)

    # Avoid duplicate handlers in dev reload
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    logger.addHandler(stream_handler)

    return logger


logger = setup_logger()
