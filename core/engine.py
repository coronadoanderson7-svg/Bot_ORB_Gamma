"""
The Core Trading Engine.

This class acts as the main orchestrator for the trading bot. It manages the
application's state and coordinates all the major components, such as the
IB client, strategy modules, and order execution manager.

The engine operates as a state machine, progressing through the stages
defined in the project summary.
"""
import time
from datetime import datetime, timedelta
from queue import Empty
from dataclasses import dataclass

# IB API imports
from ibapi.contract import Contract

# Project imports
from .logging_setup import logger
from .config_loader import APP_CONFIG
from ib_client.connector import IBConnector
from opening_range import OpeningRangeStrategy, BarLike as OpeningRangeBar
from breakout import BreakoutStrategy, BarLike as BreakoutBar

# A simple, consistent bar data model for internal use
@dataclass
class Bar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int

# Ensure our internal Bar class is compatible with strategy protocols
assert issubclass(Bar, OpeningRangeBar)
assert issubclass(Bar, BreakoutBar)

class Engine:
    """
    The main application engine that orchestrates the trading bot's lifecycle.
    It's a state machine that drives the trading strategy.
    """
    def __init__(self):
        """Initializes the Engine."""
        logger.info("Initializing Trading Engine...")
        self.config = APP_CONFIG
        self.state = "INITIALIZING"

        self.ib_connector = IBConnector()
        self.orb_strategy = OpeningRangeStrategy.from_config(self.config)
        self.breakout_strategy = BreakoutStrategy.from_config(self.config)

        # State variables
        self.contract = self._create_contract()
        self.orb_high: float = 0.0
        self.orb_low: float = 0.0
        self.next_req_id = 0

        logger.info(f"Engine initialized. Trading Mode: {self.config.account.type.upper()}, Ticker: {self.config.instrument.ticker}")

    def get_next_req_id(self):
        """Generates a unique request ID."""
        self.next_req_id += 1
        return self.next_req_id

    def _create_contract(self) -> Contract:
        """Creates the primary contract object from config."""
        contract = Contract()
        contract.symbol = self.config.instrument.ticker
        contract.secType = "STK" # Assuming Stock for now, adjust if needed (e.g., "IND" for indices)
        contract.exchange = self.config.instrument.exchange
        contract.currency = self.config.instrument.currency
        return contract

    def run(self):
        """Starts the main event loop of the trading engine."""
        logger.info("Starting engine event loop...")
        self.state = "CONNECTING"
        
        try:
            while self.state != "SHUTDOWN":
                self._process_state()
                time.sleep(1) # Main loop delay to prevent busy-waiting

        except KeyboardInterrupt:
            logger.warning("Keyboard interrupt detected. Shutting down.")
        except Exception as e:
            logger.exception(f"An unhandled exception occurred in the engine: {e}")
        finally:
            self.shutdown()

    def _process_state(self):
        """The core state machine logic."""
        logger.info(f"--- Processing State: {self.state} ---")

        if self.state == "CONNECTING":
            self._state_connect()
        elif self.state == "GETTING_OPENING_RANGE":
            self._state_get_opening_range()
        elif self.state == "MONITORING_BREAKOUT":
            self._state_monitor_for_breakout()
        elif self.state == "SHUTDOWN":
            return
        else:
            logger.error(f"Unknown state: {self.state}. Shutting down.")
            self.state = "SHUTDOWN"

    def _state_connect(self):
        """Handles connection to IBKR."""
        try:
            self.ib_connector.connect()
            if self.ib_connector.is_connected():
                self.state = "GETTING_OPENING_RANGE"
        except ConnectionError as e:
            logger.error(f"Connection failed: {e}. Retrying in 10 seconds...")
            time.sleep(10)

    def _state_get_opening_range(self):
        """Executes Stage 1: Opening Range Identification."""
        # --- 1. Wait until the opening range period has passed ---
        market_open_time = datetime.strptime(self.config.opening_range.market_open_time, "%H:%M:%S").time()
        today = datetime.now().date()
        market_open_dt = datetime.combine(today, market_open_time)
        range_end_dt = market_open_dt + timedelta(minutes=self.config.opening_range.duration_minutes)

        if datetime.now() < range_end_dt:
            wait_seconds = (range_end_dt - datetime.now()).total_seconds()
            logger.info(f"Waiting for opening range to complete. Sleeping for {wait_seconds:.0f} seconds.")
            time.sleep(wait_seconds + 5) # Add a 5-second buffer

        # --- 2. Build the request with correct parameters ---
        req_id = self.get_next_req_id()
        
        # Correctly format endDateTime and durationStr
        end_date_time_str = range_end_dt.strftime("%Y%m%d %H:%M:%S")
        duration_seconds = self.config.opening_range.duration_minutes * 60
        duration_str = f"{duration_seconds} S"
        bar_size = self.config.opening_range.bar_size
        
        logger.info(f"Requesting historical data for opening range. End: {end_date_time_str}, Duration: {duration_str}")
        self.ib_connector.req_historical_data(
            req_id, self.contract, end_date_time=end_date_time_str, duration_str=duration_str,
            bar_size_setting=bar_size, what_to_show="TRADES", use_rth=1, format_date=1, keep_up_to_date=False
        )

        # --- 3. Process the data from the queue ---
        try:
            bars_received = []
            while True:
                # Use a short timeout to prevent blocking indefinitely if the queue is empty before the sentinel
                reqId, data = self.ib_connector.wrapper.historical_data_queue.get(timeout=20)
                
                if data is None: # Sentinel value marks the end
                    logger.info("End of historical data stream received.")
                    break
                
                bar = Bar(
                    timestamp=datetime.strptime(data.date, "%Y%m%d %H:%M:%S"),
                    open=data.open, high=data.high, low=data.low, close=data.close, volume=data.volume
                )
                bars_received.append(bar)

            # Feed bars to strategy *after* collecting them all
            for bar in bars_received:
                self.orb_strategy.add_bar(bar)

            # Calculate levels and transition state
            high, low = self.orb_strategy.calculate_levels()
            if high and low:
                self.orb_high, self.orb_low = high, low
                self.state = "MONITORING_BREAKOUT"
            else:
                logger.error("Failed to calculate opening range from received bars. Shutting down.")
                self.state = "SHUTDOWN"

        except Empty:
            logger.error("Timeout waiting for historical data. Check connection and contract details. Shutting down.")
            self.state = "SHUTDOWN"

    def _state_monitor_for_breakout(self):
        """Executes Stage 2: Breakout Detection."""
        req_id = self.get_next_req_id()
        logger.info(f"Requesting 5-second real-time bars to monitor for breakout.")
        self.ib_connector.req_real_time_bars(req_id, self.contract, 5, "TRADES", True)

        try:
            while self.state == "MONITORING_BREAKOUT":
                reqId, data = self.ib_connector.wrapper.realtime_bar_queue.get(timeout=60)
                
                bar = Bar(
                    timestamp=datetime.fromtimestamp(data['time']),
                    open=data['open'], high=data['high'], low=data['low'], close=data['close'], volume=data['volume']
                )

                signal = self.breakout_strategy.add_realtime_bar(bar, self.orb_high, self.orb_low)

                if signal != "NO SIGNAL":
                    logger.info(f"!!! BREAKOUT DETECTED: {signal} !!!")
                    logger.info("Transitioning to next stage (not implemented). Shutting down for now.")
                    # In future, would transition to "GEX_ANALYSIS" or "TRADE_EXECUTION"
                    self.state = "SHUTDOWN"
                    # self.ib_connector.cancel_real_time_bars(req_id) # Important cleanup
                    break # Exit monitoring loop

        except Empty:
            logger.warning("No real-time bars received in the last 60 seconds. Checking connection.")
            if not self.ib_connector.is_connected():
                self.state = "CONNECTING"

    def shutdown(self):
        """Gracefully shuts down the trading engine."""
        if self.state == "SHUTDOWN" and not self.ib_connector.is_connected():
            return # Already shut down
            
        logger.info("Shutting down trading engine...")
        
        # Find and cancel any active real-time bar subscriptions
        # This is a simplification; a real app would track request IDs.
        if self.next_req_id > 0:
            logger.info("Attempting to cancel all active data subscriptions.")
            for i in range(1, self.next_req_id + 1):
                self.ib_connector.cancel_real_time_bars(i)

        if self.ib_connector and self.ib_connector.is_connected():
            self.ib_connector.disconnect()
            
        self.state = "SHUTDOWN"
        logger.info("Engine has been shut down.")