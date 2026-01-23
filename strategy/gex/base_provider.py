from abc import ABC, abstractmethod
import logging
import requests
from typing import TYPE_CHECKING
from core.config_loader import Config

if TYPE_CHECKING:
    from ib_client.connector import IBConnector

logger = logging.getLogger(__name__)

class BaseGexProvider(ABC):
    """
    Abstract base class for all GEX data providers.
    It provides a common interface and shared functionality like making HTTP requests.
    """
    def __init__(self, config: Config):
        self.config = config
        self.session = requests.Session()

    def _make_request(self, url: str, params: dict = None, headers: dict = None) -> dict:
        """
        Makes an HTTP GET request and returns the JSON response.

        Args:
            url (str): The URL to request.
            params (dict, optional): URL parameters. Defaults to None.
            headers (dict, optional): Request headers. Defaults to None.

        Returns:
            dict: The JSON response from the API.

        Raises:
            requests.exceptions.RequestException: For connection errors or non-200 status codes.
        """
        try:
            response = self.session.get(url, params=params, headers=headers, timeout=10)
            response.raise_for_status()  # Raises an HTTPError for bad responses (4xx or 5xx)
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed for {url}: {e}")
            raise

    @abstractmethod
    def get_max_gamma_strike(self, ticker: str, ib_connector: "IBConnector" = None) -> tuple[float, str]:
        """
        Fetches data, calculates total gamma for each strike, and returns the
        strike with the highest concentration and its expiration date.

        Args:
            ticker (str): The underlying symbol (e.g., 'SPX').
            ib_connector ("IBConnector", optional): An instance of the IB connector.
                                                     Defaults to None. Only used by providers
                                                     that communicate directly with IBKR.

        Returns:
            tuple[float, str]: A tuple containing the max gamma strike and the
                             option expiration date (YYYYMMDD).
        """
        pass