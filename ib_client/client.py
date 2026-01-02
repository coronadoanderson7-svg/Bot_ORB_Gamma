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
