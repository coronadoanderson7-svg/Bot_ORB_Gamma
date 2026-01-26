"""
EClient implementation for the IB API.

This module contains the IBClient class, which inherits from ibapi.EClient.
EClient is responsible for sending requests to the TWS/Gateway.

This implementation is a simple pass-through to the base EClient class,
but provides a place for future customization or request hooks if needed.
"""

from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from core.logging_setup import logger

class IBClient(EClient):
    """
    The EClient implementation. This class is responsible for sending requests
    to the TWS/Gateway.
    """
    def __init__(self, wrapper: EWrapper):
        """
        Initializes the EClient.
        Args:
            wrapper: An instance of EWrapper to handle incoming messages.
        """
        EClient.__init__(self, wrapper)
        logger.info("IBClient initialized.")

    def fetch_option_chain(self, req_id: int, symbol: str, exchange: str, sec_type: str, con_id: int):
        """
        Requests the option chain for a given underlying symbol.
        The result will be handled by the securityDefinitionOptionParameter method
        in the EWrapper.
        """
        logger.info(f"Requesting option chain for {symbol} (ReqId: {req_id})")
        self.reqSecDefOptParams(req_id, symbol, exchange, sec_type, con_id)

    def fetch_market_price(self, req_id: int, contract, snapshot: bool = True, regulatory_snapshot: bool = False):
        """
        Requests a single snapshot of market data for a contract.
        The result will be handled by the tickPrice and tickSize methods
        in the EWrapper.
        """
        logger.info(f"Requesting market price for {contract.symbol} (ReqId: {req_id})")
        self.reqMktData(req_id, contract, "", snapshot, regulatory_snapshot, [])
