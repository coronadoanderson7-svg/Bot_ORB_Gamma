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
from typing import TYPE_CHECKING
from core.logging_setup import logger

if TYPE_CHECKING:
    from .connector import IBConnector

class IBWrapper(EWrapper):
    """
    The EWrapper implementation. This class handles callbacks from the TWS/Gateway
    and places relevant information into queues for processing.
    """
    def __init__(self, connector: "IBConnector"):
        super().__init__()
        self.connector = connector
        self.contract_details_queue = Queue()
        self.historical_data_queue = Queue()
        self.realtime_bar_queue = Queue()
        self.error_queue = Queue()
        self.next_valid_id_queue = Queue()
        self.option_greeks_queue = Queue()
        self.tick_size_queue = Queue()
        self.tick_price_queue = Queue()
        self.sec_def_opt_params_queue = Queue()
        self.order_status_queue = Queue()
        self.open_order_queue = Queue()
        self.execution_details_queue = Queue()
        self.position_queue = Queue()
        self.tick_snapshot_end_queue = Queue()
        
        # Internal state for assembling fragmented data
        self._historical_data = {}
        self._option_chain_data = {}

    def error(self, *args):
        """
        Handles error messages from TWS. This is a unified handler to accommodate
        the different signatures used by the EClient and Protobuf decoders.
        - Legacy signature: (reqId, errorCode, errorString)
        - Modern EClient signature: (reqId, errorCode, errorString, advancedOrderRejectJson)
        - Protobuf signature: (reqId, errorTime, errorCode, errorString, advancedOrderRejectJson)
        """
        # Set default values
        reqId, errorCode, errorString, advancedOrderRejectJson = -1, 0, "", ""

        # Unpack arguments based on length
        if len(args) == 5:  # Protobuf signature from the traceback
            reqId, _errorTime, errorCode, errorString, advancedOrderRejectJson = args
        elif len(args) == 4:  # Modern EClient signature
            reqId, errorCode, errorString, advancedOrderRejectJson = args
        elif len(args) == 3:  # Legacy signature
            reqId, errorCode, errorString = args
        else:
            logger.error(f"IB Error: Received error with unknown signature: {args}")
            self.error_queue.put((-1, -1, f"Unknown error signature: {args}"))
            return

        # This logic is from the original implementation.
        # Codes 2100-2110 and 2158 are informational.
        if 2100 <= errorCode <= 2110 or errorCode in [2158]:
            log_msg = f"IB Info: ReqId: {reqId}, Code: {errorCode}, Msg: {errorString}"
            if advancedOrderRejectJson:
                log_msg += f" | AdvancedReject: {advancedOrderRejectJson}"
            logger.info(log_msg)
            self.error_queue.put((reqId, errorCode, errorString))
        else:
            # For actual errors, call the base class's error handler which prints to stderr,
            # and also log it through our own logger.
            super().error(reqId, errorCode, errorString, advancedOrderRejectJson)
            log_msg = f"IB Error: ReqId: {reqId}, Code: {errorCode}, Msg: {errorString}"
            if advancedOrderRejectJson:
                log_msg += f" | AdvancedReject: {advancedOrderRejectJson}"
            logger.error(log_msg)
            # The original code put a 3-tuple on the queue. We maintain that contract
            # to avoid breaking the consumer of the queue.
            self.error_queue.put((reqId, errorCode, errorString))
            
    def connectionClosed(self):
        """
        Handles the event of a lost connection to TWS/Gateway.
        """
        super().connectionClosed()
        logger.warning("Connection to IB TWS/Gateway lost. Notifying connector.")
        self.connector._on_connection_closed()
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
        This method aggregates bars for a request until historicalDataEnd is called.
        """
        if reqId not in self._historical_data:
            self._historical_data[reqId] = []
        self._historical_data[reqId].append(bar)

    def historicalDataEnd(self, reqId: int, start: str, end: str):
        """
        Signals the end of a historical data stream.
        The fully assembled list of bars is now put on the queue.
        """
        super().historicalDataEnd(reqId, start, end)
        logger.debug(f"HistoricalDataEnd ReqId: {reqId}")
        if reqId in self._historical_data:
            self.historical_data_queue.put((reqId, self._historical_data[reqId]))
            del self._historical_data[reqId]
        else:
            self.historical_data_queue.put((reqId, [])) # No bars received

    def realtimeBar(self, reqId: int, time: int, open_: float, high: float, low: float, close: float,
                    volume: int, wap: float, count: int):
        """
        Callback for real-time bar data.
        """
        super().realtimeBar(reqId, time, open_, high, low, close, volume, wap, count)
        
        bar_data = {
            "time": time,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "wap": wap,
            "count": count
        }
        logger.debug(f"RealTimeBar ReqId: {reqId} : {bar_data}")
        self.realtime_bar_queue.put((reqId, bar_data))
        
    def contractDetails(self, reqId: int, contractDetails):
        """
        Receives contract details.
        """
        super().contractDetails(reqId, contractDetails)
        self.contract_details_queue.put((reqId, contractDetails))

    def contractDetailsEnd(self, reqId: int):
        """
        Signals the end of a contract details stream.
        """
        super().contractDetailsEnd(reqId)
        self.contract_details_queue.put((reqId, None)) # Sentinel value

    def tickOptionComputation(self, reqId: int, tickType: int, tickAttrib: int, impliedVol: float, delta: float, optPrice: float, pvDividend: float, gamma: float, vega: float, theta: float, undPrice: float):
        """
        Callback for option specific data (Greeks, IV).
        """
        super().tickOptionComputation(reqId, tickType, tickAttrib, impliedVol, delta, optPrice, pvDividend, gamma, vega, theta, undPrice)
        data = {
            "tickType": tickType,
            "impliedVol": impliedVol,
            "delta": delta,
            "optPrice": optPrice,
            "gamma": gamma,
            "vega": vega,
            "theta": theta,
            "undPrice": undPrice
        }
        # logger.debug(f"OptionComputation ReqId: {reqId} Data: {data}")
        self.option_greeks_queue.put((reqId, data))

    def tickSize(self, reqId: int, tickType: int, size):
        """
        Callback for size-related ticks.
        Tick Types 27 (Call OI) and 28 (Put OI) are key for GEX.
        """
        super().tickSize(reqId, tickType, size)
        # The 'size' can come as a string or Decimal from the API.
        # Convert to int immediately for consistent data types downstream.
        try:
            int_size = int(size)
            self.tick_size_queue.put((reqId, tickType, int_size))
        except (ValueError, TypeError):
            logger.warning(f"Could not convert tickSize 'size' to int. ReqId: {reqId}, TickType: {tickType}, Size: {size}")

    def tickPrice(self, reqId: int, tickType: int, price: float, attrib):
        """
        Callback for price-related ticks (Last, Bid, Ask, etc.).
        """
        super().tickPrice(reqId, tickType, price, attrib)
        self.tick_price_queue.put((reqId, tickType, price, attrib))

    def tickSnapshotEnd(self, reqId: int):
        """
        Signals the end of a snapshot data request.
        """
        super().tickSnapshotEnd(reqId)
        logger.debug(f"TickSnapshotEnd received for ReqId: {reqId}")
        self.tick_snapshot_end_queue.put(reqId)

    def securityDefinitionOptionParameter(self, reqId: int, exchange: str, underlyingConId: int, tradingClass: str, multiplier: str, expirations, strikes):
        """
        Callback for receiving option chain structure (strikes and expirations).
        This method aggregates the data before putting it on the queue.
        """
        super().securityDefinitionOptionParameter(reqId, exchange, underlyingConId, tradingClass, multiplier, expirations, strikes)
        if reqId not in self._option_chain_data:
            self._option_chain_data[reqId] = {
                "exchange": exchange,
                "underlyingConId": underlyingConId,
                "tradingClass": tradingClass,
                "multiplier": multiplier,
                "expirations": set(),
                "strikes": set()
            }
        
        # Expirations and strikes can be sent in chunks
        self._option_chain_data[reqId]["expirations"].update(expirations)
        self._option_chain_data[reqId]["strikes"].update(strikes)

    def securityDefinitionOptionParameterEnd(self, reqId: int):
        """
        Signals the end of option chain data. The fully assembled data is now
        put on the queue.
        """
        super().securityDefinitionOptionParameterEnd(reqId)
        if reqId in self._option_chain_data:
            # Convert sets to sorted lists for consistent output
            self._option_chain_data[reqId]["expirations"] = sorted(list(self._option_chain_data[reqId]["expirations"]))
            self._option_chain_data[reqId]["strikes"] = sorted(list(self._option_chain_data[reqId]["strikes"]))
            
            # Put the complete data onto the queue and clean up
            self.sec_def_opt_params_queue.put((reqId, self._option_chain_data[reqId]))
            del self._option_chain_data[reqId]
        else:
            logger.warning(f"Received OptionParameterEnd for unknown reqId: {reqId}")
            # Put a sentinel value to unblock any waiting consumer
            self.sec_def_opt_params_queue.put((reqId, None))

    def orderStatus(self, orderId: int, status: str, filled: float, remaining: float, avgFillPrice: float, permId: int, parentId: int, lastFillPrice: float, clientId: int, whyHeld: str, mktCapPrice: float):
        """
        Callback for order status updates (Submitted, Filled, Cancelled).
        Puts a dictionary with relevant info onto the order status queue.
        """
        super().orderStatus(orderId, status, filled, remaining, avgFillPrice, permId, parentId, lastFillPrice, clientId, whyHeld, mktCapPrice)
        
        status_data = {
            "orderId": orderId,
            "status": status,
            "filled": filled,
            "remaining": remaining,
            "avgFillPrice": avgFillPrice,
            "parentId": parentId
        }
        
        logger.info(f"Order Status Update: {status_data}")

        self.order_status_queue.put(status_data)

    def openOrder(self, orderId: int, contract, order, orderState):
        """
        Callback for current open orders.
        """
        super().openOrder(orderId, contract, order, orderState)
        self.open_order_queue.put((orderId, contract, order, orderState))

    def execDetails(self, reqId: int, contract, execution):
        """
        Callback for trade execution details.
        """
        super().execDetails(reqId, contract, execution)
        self.execution_details_queue.put((reqId, contract, execution))

    def position(self, account: str, contract, position: float, avgCost: float):
        """
        Callback for current portfolio positions.
        """
        super().position(account, contract, position, avgCost)
        self.position_queue.put((account, contract, position, avgCost))

    def positionEnd(self):
        """
        Signals the end of the position list.
        """
        super().positionEnd()
        self.position_queue.put(None)
