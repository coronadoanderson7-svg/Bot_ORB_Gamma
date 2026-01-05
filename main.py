"""
main.py

This is the primary entry point for the trading bot application.
It initializes the core trading engine and starts its execution loop.
"""

from core.engine import Engine
from core.logging_setup import logger
import sys

def main():
    """
    Main function to initialize and run the trading bot.
    """
    logger.info("Starting the trading bot application.")
    engine = None
    try:
        engine = Engine()
        engine.run()
    except KeyboardInterrupt:
        logger.info("Application stopped by user (KeyboardInterrupt).")
    except Exception as e:
        logger.exception(f"An unhandled error occurred: {e}")
        sys.exit(1)
    finally:
        if engine:
            logger.info("Shutting down the trading bot.")
            engine.shutdown() # Ensure proper cleanup

if __name__ == "__main__":
    main()
