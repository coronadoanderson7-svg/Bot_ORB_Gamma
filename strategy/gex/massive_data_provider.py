# strategy/gex/massive_data_provider.py

import logging
from collections import defaultdict
from pydantic import ValidationError

from core.config_loader import AppConfig
from strategy.gex.base_provider import BaseGexProvider
from strategy.gex.models import MassiveDataResponse
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ib_client.connector import IBConnector

logger = logging.getLogger(__name__)

class MassiveDataProvider(BaseGexProvider):
    """
    GEX provider for massive.com.
    Implements the BaseGexProvider to fetch and process gamma exposure data from a dedicated data feed.
    """
    def __init__(self, config: AppConfig):
        """
        Initializes the MassiveDataProvider with the application's configuration.

        Args:
            config (Config): The global configuration object.
        """
        super().__init__(config)
        provider_config = self.config.gex.providers.massive_data
        self.base_url = provider_config.base_url
        self.api_key = provider_config.api_key

    def get_max_gamma_strike(self, ticker: str, ib_connector: "IBConnector" = None) -> tuple[float, str]:
        """
        Fetches options chain data from massive.com, calculates total gamma exposure
        for each strike, and returns the strike with the highest concentration.

        Args:
            ticker (str): The underlying symbol (e.g., 'SPX').
            ib_connector ("IBConnector", optional): Not used by this provider.

        Returns:
            tuple[float, str]: A tuple containing the max gamma strike and the
                             option expiration date in 'YYYYMMDD' format.
                             Returns (0.0, "") if an error occurs.
        """
        # a. Connect & Fetch
        endpoint = f"{self.base_url}/options/chain"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        params = {
            "ticker": ticker,
            "days_to_expiration": self.config.gex.days_to_expiration,
            "strikes_quantity": self.config.gex.strikes_quantity,
            "fields": "greeks,openInterest"
        }
        logger.info(f"Requesting GEX data for {ticker} from Massive Data with DTE={params['days_to_expiration']}.")

        try:
            response_json = self._make_request(endpoint, params=params, headers=headers)

            # c. Parse Data
            parsed_data = MassiveDataResponse.parse_obj(response_json)
            
            # d. Calculate Gamma Exposure
            gamma_by_strike = defaultdict(float)
            option_multiplier = self.config.gex.option_multiplier

            for option in parsed_data.options:
                if option.greeks and option.open_interest is not None:
                    gamma_exposure = option.greeks.gamma * option.open_interest * option_multiplier
                    gamma_by_strike[option.strike] += gamma_exposure

            if not gamma_by_strike:
                logger.warning(f"No valid options data found for {ticker} to calculate GEX.")
                return 0.0, ""

            # e. Find Max & Return
            max_gamma_strike = max(gamma_by_strike, key=gamma_by_strike.get)
            expiration_date = parsed_data.expiration.replace("-", "")

            logger.info(f"Found max GEX strike: {max_gamma_strike} with Total GEX: {gamma_by_strike[max_gamma_strike]:.2f}")
            return max_gamma_strike, expiration_date

        except (ValidationError, Exception) as e:
            logger.error(f"Could not retrieve or process GEX data from massive.com for {ticker}: {e}", exc_info=True)
            return 0.0, ""