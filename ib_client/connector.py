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
from queue import Empty, Queue
from ibapi.contract import Contract

from .wrapper import IBWrapper
from .client import IBClient
from core.logging_setup import logger
from core.config_loader import APP_CONFIG

# A mapping from IB tick type codes to human-readable names
# Price tick types
TICK_TYPE_MAP = {
    1: 'bid',
    2: 'ask',
    4: 'last',
    6: 'high',
    7: 'low',
    9: 'close',
    # Size tick types
    0: 'bid_size',
    3: 'ask_size',
    5: 'last_size',
    8: 'volume',
}


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
        self._next_request_id = 0
        self._request_id_lock = threading.Lock()

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
            next_id = self.wrapper.next_valid_id_queue.get(timeout=timeout)
            with self._request_id_lock:
                self._next_request_id = next_id
            
            self._is_connected = True
            logger.info(f"Connection established successfully. Next Request ID seed: {next_id}")
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

    def get_next_request_id(self, count: int = 1) -> int:
        """
        Returns the next valid request ID in a thread-safe manner.
        This is the single source of truth for all request IDs.

        Args:
            count: The number of IDs to reserve.
        """
        if not self.is_connected():
            logger.error("Cannot get next request ID, not connected.")
            return -1
        
        with self._request_id_lock:
            current_id = self._next_request_id
            self._next_request_id += count
        return current_id

    def fetch_option_chain(self, symbol: str, timeout: int = 20) -> list[float]:
        """
        Fetches the option chain (strikes) for a given symbol.
        This is a blocking operation.

        Args:
            symbol: The underlying ticker symbol (e.g., 'SPX').
            timeout: Maximum seconds to wait for a response.

        Returns:
            A list of available strike prices, or an empty list.
        """
        req_id = self.get_next_request_id()
        
        underlying_contract = Contract()
        underlying_contract.symbol = symbol
        underlying_contract.secType = "STK" 
        underlying_contract.exchange = "SMART"
        underlying_contract.currency = APP_CONFIG.instrument.currency

        details = self.resolve_contract_details(underlying_contract, timeout=timeout)
        if not details:
            logger.error(f"Could not resolve contract for underlying '{symbol}' to get conId.")
            return []
        
        underlying_con_id = details.contract.conId
        
        self.client.fetch_option_chain(
            req_id=req_id,
            symbol=symbol,
            exchange="",
            sec_type=details.contract.secType,
            con_id=underlying_con_id
        )

        try:
            q_req_id, chain_data = self.wrapper.sec_def_opt_params_queue.get(timeout=timeout)
            
            if q_req_id != req_id:
                logger.error(f"Received option chain data for unexpected reqId. Expected {req_id}, got {q_req_id}.")
                return []

            if not chain_data:
                logger.warning(f"Received empty option chain data for {symbol}.")
                return []
            
            strikes = chain_data.get('strikes', [])
            logger.info(f"Successfully fetched {len(strikes)} strikes for {symbol}.")
            return strikes

        except Empty:
            logger.error(f"Timeout fetching option chain for {symbol}. No response from TWS.")
            return []

    def fetch_market_price(self, contract, timeout: int = 5) -> dict:
        """
        Fetches a snapshot of the current market price for a given contract.
        This is a blocking operation.

        Args:
            contract: The ibapi.contract.Contract object.
            timeout: Maximum seconds to wait for a response.

        Returns:
            A dictionary containing the latest market data (e.g., 'bid', 'ask', 'last').
        """
        req_id = self.get_next_request_id()
        self.client.fetch_market_price(req_id, contract)

        market_data = {}
        end_time = time.time() + timeout

        try:
            # Drain queues of old data before starting
            while not self.wrapper.tick_price_queue.empty():
                self.wrapper.tick_price_queue.get_nowait()
            while not self.wrapper.tick_size_queue.empty():
                self.wrapper.tick_size_queue.get_nowait()

            while time.time() < end_time:
                try:
                    # Check for price ticks
                    p_req_id, p_tick_type, price, _ = self.wrapper.tick_price_queue.get(block=True, timeout=0.1)
                    if p_req_id == req_id:
                        key = TICK_TYPE_MAP.get(p_tick_type)
                        if key:
                            market_data[key] = price
                except Empty:
                    pass  # No price data currently in queue

                try:
                    # Check for size ticks
                    s_req_id, s_tick_type, size = self.wrapper.tick_size_queue.get(block=True, timeout=0.1)
                    if s_req_id == req_id:
                        key = TICK_TYPE_MAP.get(s_tick_type)
                        if key:
                            market_data[key] = size
                except Empty:
                    pass  # No size data currently in queue
                
                # Heuristic to exit early if we have the most common data points
                if all(k in market_data for k in ['bid', 'ask', 'last']):
                    break

        except Exception as e:
            logger.exception(f"Exception while fetching market price for {contract.symbol}: {e}")

        if not market_data:
            logger.warning(f"Timeout or no market data received for {contract.symbol} within {timeout}s.")
        else:
            logger.info(f"Successfully fetched market price snapshot for {contract.symbol}: {market_data}")

        # The market data request for a snapshot is automatically cancelled by TWS.
        return market_data
            
    # --- Placeholder methods for data and order operations ---

    def resolve_contract_details(self, contract, timeout: int = 10):
        """
        Resolves a contract to get its full details, including conId.
        This is a blocking operation.

        Args:
            contract: An ibapi.contract.Contract with enough info to be unique.
            timeout: Max seconds to wait for a response.

        Returns:
            The first matching ibapi.contract.ContractDetails object, or None.
        """
        req_id = self.get_next_request_id()
        self.req_contract_details(req_id, contract)

        try:
            # Wait for the first result or timeout
            q_req_id, details = self.wrapper.contract_details_queue.get(timeout=timeout)

            if q_req_id != req_id:
                logger.error(f"Received contract details for unexpected reqId.")
                return None

            # The API may send multiple matches. We will take the first one.
            # We must also consume the "End" signal from the queue.
            while True:
                try:
                    end_req_id, _ = self.wrapper.contract_details_queue.get(timeout=1)
                    if end_req_id == req_id:
                        break # Found the end for our request
                except Empty:
                    logger.warning(f"Did not find contractDetailsEnd message for reqId {req_id}.")
                    break
            
            if details:
                logger.info(f"Resolved contract for {contract.symbol}. ConId: {details.contract.conId}")
                return details
            else:
                logger.warning(f"Could not resolve contract for {contract.symbol}. Received empty details.")
                return None

        except Empty:
            logger.error(f"Timeout resolving contract for {contract.symbol}. No response from TWS.")
            return None


    # --- Data Request Methods ---

    def req_contract_details(self, req_id: int, contract):
        """
        Requests contract details for a given contract.
        """
        logger.info(f"Requesting contract details. ReqId: {req_id}, Symbol: {contract.symbol}")
        self.client.reqContractDetails(req_id, contract)

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

    def _format_order_details(self, contract, order, order_id) -> str:
        """Helper to create a detailed log string for an order."""
        details = [
            f"Placing OrderId: {order_id}",
            f"Action: {order.action}",
            f"Qty: {order.totalQuantity}",
            f"Symbol: {contract.symbol}",
            f"SecType: {contract.secType}",
        ]
        if contract.secType == "OPT":
            details.extend([
                f"Strike: {contract.strike}",
                f"Right: {contract.right}",
                f"Expiry: {contract.lastTradeDateOrContractMonth}",
            ])
        details.extend([
            f"OrderType: {order.orderType}",
            f"TIF: {order.tif}",
        ])
        if order.orderType == "LMT" and order.lmtPrice > 0:
            details.append(f"LmtPrice: {order.lmtPrice}")
        if order.orderType in ["STP", "STP LMT"] and order.auxPrice > 0:
            details.append(f"AuxPrice: {order.auxPrice}")
        if order.parentId:
            details.append(f"ParentId: {order.parentId}")
            
        return ", ".join(details)

    def place_order(self, contract, order, order_id: int = None):
        """
        Places an order. If order_id is provided, it will be used to modify an
        existing order. For new orders, the orderId from the Order object is used.
        """
        # For modifications, an explicit order_id is passed.
        # For new orders, we use the orderId from the Order object itself.
        id_to_use = order_id if order_id is not None else order.orderId

        log_str = self._format_order_details(contract, order, id_to_use)
        logger.info(log_str)
        
        self.client.placeOrder(id_to_use, contract, order)
        return id_to_use

    def get_order_status_queue(self) -> Queue:
        """
        Returns the queue for order status messages.
        """
        return self.wrapper.order_status_queue

    def req_positions(self):
        """
        Requests current positions. The results will be sent to the position queue.
        """
        logger.info("Requesting current account positions.")
        self.client.reqPositions()

    def get_positions(self, timeout: int = 5) -> list:
        """
        Retrieves all current positions from the queue.
        This is a blocking call that waits for the 'positionEnd' sentinel.
        """
        positions = []
        try:
            # First item might be a position or the end sentinel
            item = self.wrapper.position_queue.get(timeout=timeout)
            while item is not None:
                positions.append(item)
                item = self.wrapper.position_queue.get(timeout=timeout)
            return positions
        except Empty:
            logger.warning("Timeout or empty queue while fetching positions.")
            return positions # Return any positions received before timeout

    def get_execution_details(self, req_id: int, timeout: int = 10) -> tuple:
        """
        Retrieves execution details for a specific request ID.
        This is a blocking call.
        """
        try:
            # Note: The default execDetails does not use reqId, but we can filter
            # if we match it with orderId. For now, we get the next available.
            q_req_id, contract, execution = self.wrapper.execution_details_queue.get(timeout=timeout)
            # This is a simplification. A real system needs a robust way to match
            # executions to requests, likely by orderId.
            return contract, execution
        except Empty:
            return None, None
