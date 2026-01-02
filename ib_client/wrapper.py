"""
EWrapper implementation for the IB API.

This module contains the IBWrapper class, which inherits from ibapi.EWrapper.
Its primary responsibility is to handle all incoming messages from the TWS/Gateway,
such as error messages, connection status, and market data.

To ensure thread safety and decouple the wrapper from the business logic, this
class places incoming data and messages onto thread-safe queues. The IBConnector
class then consumes these messages from the other side of the queue.
"""

from ibapi.wrapper import EWrapper
from queue import Queue
from core.logging_setup import logger

class IBWrapper(EWrapper):
    """
    The EWrapper implementation. This class handles callbacks from the TWS/Gateway
    and places relevant information into queues for processing.
    """
    def __init__(self):
        super().__init__()
        self.contract_details_queue = Queue()
        self.historical_data_queue = Queue()
        self.realtime_bar_queue = Queue()
        self.error_queue = Queue()
        self.next_valid_id_queue = Queue()

    def error(self, reqId: int, errorCode: int, errorString: str, advancedOrderReject=""):
        """
        Handles error messages from TWS.
        - reqId -1 indicates a system-level message, not related to a specific request.
        """
        super().error(reqId, errorCode, errorString, advancedOrderReject)
        # IB's "error" callback is also used for informational messages.
        # Codes 2100-2110 are info messages about connectivity.
        # We will log them as INFO and not put them in the error queue to avoid
        # treating them as critical failures.
        if 2100 <= errorCode <= 2110 or errorCode in [2158]:
            logger.info(f"IB Info: ReqId: {reqId}, Code: {errorCode}, Msg: {errorString}")
        else:
            logger.error(f"IB Error: ReqId: {reqId}, Code: {errorCode}, Msg: {errorString}")
            self.error_queue.put((reqId, errorCode, errorString))
            
    def connectionClosed(self):
        """
        Handles the event of a lost connection to TWS/Gateway.
        """
        super().connectionClosed()
        logger.warning("Connection to IB TWS/Gateway lost.")
        self.error_queue.put((-1, -1, "Connection lost"))

    def nextValidId(self, orderId: int):
        """
        Receives the next valid order ID at connection time.
        This is a crucial marker for a successful connection.
        """
        super().nextValidId(orderId)
        logger.info(f"Successfully connected to IB. Next valid Order ID: {orderId}")
        self.next_valid_id_queue.put(orderId)

    # --- Placeholder methods for data handling ---
    # These will be fleshed out as we build the strategy modules.

    def historicalData(self, reqId: int, bar):
        """
        Callback for historical data requests.
        """
        logger.debug(f"HistoricalData ReqId: {reqId}, Bar: {bar}")
        # self.historical_data_queue.put((reqId, bar))

    def historicalDataEnd(self, reqId: int, start: str, end: str):
        """
        Signals the end of a historical data stream.
        """
        super().historicalDataEnd(reqId, start, end)
        logger.debug(f"HistoricalDataEnd ReqId: {reqId}")
        # self.historical_data_queue.put((reqId, None)) # Sentinel value

    def realtimeBar(self, reqId: int, time: int, open_: float, high: float, low: float, close: float,
                    volume: int, wap: float, count: int):
        """
        Callback for real-time bar data.
        """
        super().realtimeBar(reqId, time, open_, high, low, close, volume, wap, count)
        logger.debug(f"RealTimeBar ReqId: {reqId}")
        # self.realtime_bar_queue.put((reqId, bar_data))
        
    def contractDetails(self, reqId: int, contractDetails):
        """
        Receives contract details.
        """
        super().contractDetails(reqId, contractDetails)
        # self.contract_details_queue.put((reqId, contractDetails))

    def contractDetailsEnd(self, reqId: int):
        """
        Signals the end of a contract details stream.
        """
        super().contractDetailsEnd(reqId)
        # self.contract_details_queue.put((reqId, None)) # Sentinel value
