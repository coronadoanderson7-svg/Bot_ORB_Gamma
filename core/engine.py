"""
The Core Trading Engine.

This class acts as the main orchestrator for the trading bot. It manages the
application's state and coordinates all the major components, such as the
IB client, strategy modules, and order execution manager.

The engine operates as a state machine, progressing through the stages
defined in the project summary.
"""

from .logging_setup import logger
from .config_loader import APP_CONFIG

class Engine:
    """
    The main application engine that orchestrates the trading bot's lifecycle.
    """
    def __init__(self):
        """
        Initializes the Engine.
        """
        logger.info("Initializing Trading Engine...")
        self.config = APP_CONFIG
        self.state = "INITIALIZING"
        
        # Placeholder for other components that will be initialized later
        self.ib_connector = None
        self.strategy_manager = None
        self.order_manager = None

        logger.info(f"Engine initialized in '{self.state}' state.")
        logger.info(f"Trading Mode: {self.config.account.type.upper()}")
        logger.info(f"Ticker: {self.config.instrument.ticker}")


    def run(self):
        """
        Starts the main event loop of the trading engine.
        """
        logger.info("Starting engine event loop...")
        self.state = "STARTING"
        
        try:
            # This is where the main state machine loop will reside.
            # For now, it's just a placeholder.
            
            # 1. Connect to IBKR
            # self.connect_to_ib()
            
            # 2. Schedule task to wait for market open
            # self.await_market_open()

            # 3. Main loop (driven by schedule or an async loop)
            # while self.state != "SHUTDOWN":
            #    self.process_state()
            #    time.sleep(1) # Or await async event

            logger.info("Engine run loop placeholder finished.")

        except KeyboardInterrupt:
            logger.warning("Keyboard interrupt detected. Shutting down engine.")
        except Exception as e:
            logger.exception(f"An unhandled exception occurred in the engine: {e}")
        finally:
            self.shutdown()


    def shutdown(self):
        """
        Gracefully shuts down the trading engine.
        """
        logger.info("Shutting down trading engine...")
        self.state = "SHUTDOWN"
        
        # Disconnect from IBKR
        # if self.ib_connector and self.ib_connector.is_connected():
        #     self.ib_connector.disconnect()
            
        logger.info("Engine has been shut down.")

# Example of how to run the engine (will be called from main.py)
if __name__ == '__main__':
    # This is for testing purposes. The main entry point is main.py
    engine = Engine()
    engine.run()
