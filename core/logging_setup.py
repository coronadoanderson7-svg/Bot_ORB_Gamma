"""
Configures the Loguru logger for the application.

This module sets up logging to both the console and a file, based on the
settings defined in the `config.yaml` file.

The configured `logger` object should be imported by all other modules
in the application to ensure consistent logging behavior.
"""

import sys
from loguru import logger
from .config_loader import APP_CONFIG

# Get logging settings from the validated configuration
log_config = APP_CONFIG.logging

# 1. Remove the default Loguru handler to prevent duplicate console outputs.
logger.remove()

# 2. Add a handler for console (stdout) logging.
#    This provides immediate feedback during development and execution.
logger.add(
    sys.stdout,
    level=log_config.log_level.upper(),
    format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
)

# 3. Add a handler for file-based logging.
#    This creates a persistent record of the bot's activity.
logger.add(
    log_config.log_file,
    level=log_config.log_level.upper(),
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
    rotation="10 MB",  # Rotates the log file when it reaches 10 MB
    retention="7 days",# Keeps logs for up to 7 days
    enqueue=True,      # Makes logging thread-safe
    backtrace=True,    # Shows full stack trace on exceptions
    diagnose=True      # Adds exception data for easier debugging
)

logger.info("Logger initialized successfully.")
