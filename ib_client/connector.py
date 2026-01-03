"""
High-level connector for the Interactive Brokers API.

This module provides the IBConnector class, which is the primary interface
for the rest of the application to interact with the IB TWS/Gateway.

It encapsulates the EClient and EWrapper, manages the connection lifecycle,
and runs the message processing loop in a dedicated background thread.
This provides a clean, thread-safe, and simplified API for the main trading engine.
"""

import threading
import time
from queue import Empty

from .wrapper import IBWrapper
from .client import IBClient
from core.logging_setup import logger
from core.config_loader import APP_CONFIG

class IBConnector:
    """
    Manages the connection and communication with the IB TWS/Gateway.
    """
    def __init__(self):
        """
        Initializes the IBConnector.
        """
        self.wrapper = IBWrapper()
        self.client = IBClient(self.wrapper)
        
        self.host = APP_CONFIG.connection.host
        self.port = APP_CONFIG.connection.port
        self.client_id = APP_CONFIG.connection.client_id
        
        self.connection_thread = None
        self._is_connected = False
        self.next_order_id = None

        logger.info("IBConnector initialized.")

    def is_connected(self) -> bool:
        """Returns the connection status."""
        return self._is_connected

    def connect(self):
        """
        Connects to the TWS/Gateway and starts the message processing loop.
        """
        if self.is_connected():
            logger.warning("Already connected.")
            return

        logger.info(f"Connecting to IB TWS/Gateway at {self.host}:{self.port} with ClientID {self.client_id}...")
        
        try:
            # The connect call is non-blocking.
            self.client.connect(self.host, self.port, self.client_id)
            
            # Start the message processing loop in a background thread.
            self.connection_thread = threading.Thread(target=self.client.run, daemon=True)
            self.connection_thread.start()
            logger.info("Connection thread started.")
            
            # Wait for successful connection confirmation (nextValidId)
            self._wait_for_connection()

        except Exception as e:
            logger.exception(f"Failed to connect to IB: {e}")
            self.disconnect() # Ensure cleanup on failure
            raise

    def _wait_for_connection(self, timeout: int = 10):
        """
        Waits for the 'nextValidId' event, which confirms a successful connection.
        """
        logger.info("Waiting for connection to be established...")
        try:
            self.next_order_id = self.wrapper.next_valid_id_queue.get(timeout=timeout)
            self._is_connected = True
            logger.info(f"Connection established successfully. Next Order ID: {self.next_order_id}")
        except Empty:
            logger.error(f"Connection failed: Did not receive nextValidId in {timeout} seconds.")
            self.disconnect()
            raise ConnectionError("IB connection timeout.")

    def disconnect(self):
        """
        Disconnects from the TWS/Gateway and stops the message loop.
        """
        if not self.is_connected() and self.client.isConnected():
             # Case where connection attempt failed mid-way
             logger.info("Disconnecting from partially established connection.")
        elif not self.is_connected():
            logger.info("Already disconnected.")
            return
            
        logger.info("Disconnecting from IB TWS/Gateway...")
        
        self._is_connected = False
        self.client.disconnect()
        
        if self.connection_thread and self.connection_thread.is_alive():
            logger.info("Waiting for connection thread to terminate.")
            self.connection_thread.join(timeout=5)
            if self.connection_thread.is_alive():
                logger.warning("Connection thread did not terminate gracefully.")

        logger.info("Disconnected successfully.")

    # --- Placeholder methods for data and order operations ---

    def get_next_order_id(self) -> int:
        """
        Returns the next valid order ID.
        """
        if not self.next_order_id:
            logger.error("Next order ID is not available. Check connection.")
            return -1
        
        current_id = self.next_order_id
        self.next_order_id += 1
        return current_id

    # --- Data Request Methods ---

    def req_historical_data(self, req_id: int, contract, end_date_time: str, duration_str: str, bar_size_setting: str, what_to_show: str, use_rth: int, format_date: int, keep_up_to_date: bool):
        """
        Requests historical data for a contract.
        """
        logger.info(f"Requesting historical data. ReqId: {req_id}, Symbol: {contract.symbol}")
        self.client.reqHistoricalData(req_id, contract, end_date_time, duration_str, bar_size_setting, what_to_show, use_rth, format_date, keep_up_to_date, [])

    def req_real_time_bars(self, req_id: int, contract, bar_size: int, what_to_show: str, use_rth: bool):
        """
        Requests real-time bars.
        """
        logger.info(f"Requesting real-time bars. ReqId: {req_id}, Symbol: {contract.symbol}")
        self.client.reqRealTimeBars(req_id, contract, bar_size, what_to_show, use_rth, [])

    def cancel_real_time_bars(self, req_id: int):
        """
        Cancels real-time bars subscription.
        """
        logger.info(f"Cancelling real-time bars. ReqId: {req_id}")
        self.client.cancelRealTimeBars(req_id)

    def req_sec_def_opt_params(self, req_id: int, underlying_symbol: str, fut_fop_exchange: str, underlying_sec_type: str, underlying_con_id: int):
        """
        Requests security definition option parameters (strikes, expirations).
        """
        logger.info(f"Requesting option params. ReqId: {req_id}, Symbol: {underlying_symbol}")
        self.client.reqSecDefOptParams(req_id, underlying_symbol, fut_fop_exchange, underlying_sec_type, underlying_con_id)

    def req_market_data(self, req_id: int, contract, generic_tick_list: str, snapshot: bool, regulatory_snapshot: bool):
        """
        Requests market data (ticks).
        """
        logger.info(f"Requesting market data. ReqId: {req_id}, Symbol: {contract.symbol}")
        self.client.reqMktData(req_id, contract, generic_tick_list, snapshot, regulatory_snapshot, [])

    def cancel_market_data(self, req_id: int):
        """
        Cancels market data subscription.
        """
        logger.info(f"Cancelling market data. ReqId: {req_id}")
        self.client.cancelMktData(req_id)

    # --- Order Management Methods ---

    def place_order(self, order_id: int, contract, order):
        """
        Places an order.
        """
        logger.info(f"Placing order. OrderId: {order_id}, Action: {order.action}, Qty: {order.totalQuantity}, Symbol: {contract.symbol}")
        self.client.placeOrder(order_id, contract, order)

    def req_positions(self):
        """
        Requests current positions.
        """
        logger.info("Requesting positions.")
        self.client.reqPositions()
