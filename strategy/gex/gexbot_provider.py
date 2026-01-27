# strategy/gex/gexbot_provider.py

import logging
from datetime import datetime, timedelta
from pydantic import ValidationError
from core.config_loader import AppConfig
from typing import TYPE_CHECKING
from strategy.gex.base_provider import BaseGexProvider
from strategy.gex.models import GexbotResponse

if TYPE_CHECKING:
    from ib_client.connector import IBConnector

logger = logging.getLogger(__name__)

class GexbotProvider(BaseGexProvider):
    """
    GEX provider for gexbot.com.
    Implements the BaseGexProvider to fetch and process gamma exposure data.
    """
    def __init__(self, config: AppConfig):
        """
        Initializes the GexbotProvider with the application's configuration.

        Args:
            config (AppConfig): The global configuration object.
        """
        super().__init__(config)
        provider_config = self.config.gex.providers.gexbot
        self.base_url = provider_config.base_url
        self.api_key = provider_config.api_key

    def get_max_gamma_strike(self, ticker: str, ib_connector: "IBConnector" = None) -> tuple[float, str]:
        """
        Fetches GEX data from gexbot.com, calculates total gamma for each strike,
        and returns the strike with the highest concentration and its expiration date.

        Args:
            ticker (str): The underlying symbol (e.g., 'SPX').
            ib_connector ("IBConnector", optional): Not used by this provider.

        Returns:
            tuple[float, str]: A tuple containing the max gamma strike and the
                             option expiration date in 'YYYYMMDD' format.
                             Returns (0.0, "") if an error occurs.
        """
        # a. Calculate Expiration Date
        days_to_expiration = self.config.gex.days_to_expiration
        expiration_date = datetime.now() + timedelta(days=days_to_expiration)
        expiration_date_str = expiration_date.strftime('%Y-%m-%d')
        expiration_date_formatted = expiration_date.strftime('%Y%m%d')
        logger.info(f"Requesting GEX data for {ticker} with expiration {expiration_date_str}")

        # b. Connect & Fetch
        endpoint = f"{self.base_url}/gex/distribution"
        params = {
            "ticker": ticker,
            "exp": expiration_date_str,
            "api_key": self.api_key,
        }

        try:
            response_json = self._make_request(endpoint, params=params)

            # d. Parse & Aggregate
            gex_data = GexbotResponse.parse_obj(response_json)

            if not gex_data.success or not gex_data.data:
                logger.warning(f"Gexbot API returned success=false or no data for {ticker} on {expiration_date_str}.")
                return 0.0, ""

            max_gex_strike = 0.0
            max_gex_value = -1

            for strike_data in gex_data.data:
                # Calculate Total_GEX = abs(short_gamma) + abs(long_gamma)
                total_gex = abs(strike_data.short_gamma) + abs(strike_data.long_gamma)

                if total_gex > max_gex_value:
                    max_gex_value = total_gex
                    max_gex_strike = strike_data.strike
            
            if max_gex_strike == 0.0:
                logger.warning(f"No max GEX strike found for {ticker} on {expiration_date_str}.")
                return 0.0, ""

            logger.info(f"Found max GEX strike: {max_gex_strike} with Total GEX: {max_gex_value:.2f}")
            return max_gex_strike, expiration_date_formatted

        except Exception as e:
            logger.error(f"Could not retrieve or parse GEX data from gexbot.com for {ticker}: {e}", exc_info=True)
            return 0.0, ""
