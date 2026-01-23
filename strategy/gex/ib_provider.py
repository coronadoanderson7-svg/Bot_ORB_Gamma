# strategy/gex/ib_provider.py
import logging
from typing import TYPE_CHECKING, Optional, List, Tuple, Dict
from ibapi.contract import Contract
from queue import Empty
from collections import defaultdict
from datetime import datetime, timedelta

from core.config_loader import AppConfig
from strategy.gex.base_provider import BaseGexProvider

if TYPE_CHECKING:
    from ib_client.connector import IBConnector

logger = logging.getLogger(__name__)


class IBProvider(BaseGexProvider):
    """
    GEX provider that calculates GEX by fetching real-time options and market
    data directly from Interactive Brokers (IB).
    """

    def __init__(self, config: AppConfig):
        """
        Initializes the IBProvider with the application's configuration.
        """
        super().__init__(config)

    def get_max_gamma_strike(self, ticker: str, ib_connector: "IBConnector" = None) -> tuple[float, str]:
        """
        Fetches option chain and market data from IB, calculates GEX, and
        identifies the strike with the maximum gamma exposure.
        """
        if not ib_connector or not ib_connector.is_connected():
            logger.error("IBProvider cannot fetch data: IBConnector is not available or not connected.")
            return (0.0, "")

        try:
            # 1. Resolve underlying contract to get conId
            underlying_contract = self._create_underlying_contract(ticker)
            details = ib_connector.resolve_contract_details(underlying_contract)
            if not details:
                logger.error(f"Could not resolve contract for {ticker}.")
                return (0.0, "")
            underlying_con_id = details.contract.conId

            # 2. Get current price of the underlying
            underlying_price = self._fetch_underlying_price(ib_connector, underlying_contract)
            if not underlying_price:
                logger.error(f"Could not fetch underlying price for {ticker}.")
                return (0.0, "")
            logger.info(f"Underlying price for {ticker} is {underlying_price}.")

            # 3. Get all expirations and strikes for the option chain
            expirations, strikes = self._fetch_option_chain_params(ib_connector, ticker, underlying_con_id)
            if not expirations or not strikes:
                return (0.0, "")

            # 4. Filter to find the target expiration and strikes
            target_expiration = self._filter_target_expiration(expirations)
            if not target_expiration:
                return (0.0, "")
            
            target_strikes = self._filter_target_strikes(strikes, underlying_price)
            logger.info(f"Using expiration {target_expiration} and {len(target_strikes)} strikes.")

            # 5. Build contracts and request data
            option_contracts = self._build_option_contracts(ticker, target_expiration, target_strikes)
            
            req_id_map, data_aggregator = self._request_market_data(ib_connector, option_contracts)
            if not req_id_map:
                return (0.0, "")

            # 6. Collect data from queues
            self._collect_market_data(ib_connector, len(req_id_map), data_aggregator)

            # 7. Cancel subscriptions
            logger.info("Cancelling all market data subscriptions.")
            for req_id in req_id_map:
                ib_connector.cancel_market_data(req_id)

            # 8. Calculate GEX
            gex_by_strike = self._calculate_gex(req_id_map, data_aggregator)

            # 9. Find and return max GEX strike
            if not gex_by_strike:
                logger.warning("GEX calculation resulted in no data.")
                return (0.0, "")
                
            max_gex_strike = max(gex_by_strike, key=gex_by_strike.get)
            logger.info(f"Found max GEX strike: {max_gex_strike} with GEX value {gex_by_strike[max_gex_strike]:.2f}")

            return (max_gex_strike, target_expiration)

        except Exception as e:
            logger.exception(f"An unexpected error occurred during GEX calculation: {e}")
            return (0.0, "")

    def _create_underlying_contract(self, ticker: str) -> Contract:
        """Creates an ibapi.Contract for the underlying stock/index."""
        contract = Contract()
        contract.symbol = ticker
        contract.secType = "STK" if ticker not in ["SPX", "VIX"] else "IND"
        contract.exchange = self.config.instrument.exchange
        contract.currency = self.config.instrument.currency
        return contract

    def _fetch_underlying_price(self, ib_connector: "IBConnector", contract: Contract) -> Optional[float]:
        """Fetches the last price for a given contract."""
        req_id = ib_connector.get_next_request_id()
        ib_connector.req_market_data(req_id, contract, "", True, False) # Snapshot, no specific ticks needed for last price
        
        try:
            # Look for tickType 4 (last price)
            while True:
                q_req_id, q_tick_type, q_price, _ = ib_connector.wrapper.tick_price_queue.get(timeout=5)
                if q_req_id == req_id and q_tick_type == 4:
                    ib_connector.cancel_market_data(req_id)
                    return q_price
        except Empty:
            logger.error(f"Timeout fetching underlying price for {contract.symbol}.")
            return None

    def _fetch_option_chain_params(self, ib_connector: "IBConnector", ticker: str, con_id: int) -> Tuple[Optional[List[str]], Optional[List[float]]]:
        """Fetches all expirations and strikes for an underlying."""
        req_id = ib_connector.get_next_request_id()
        ib_connector.req_sec_def_opt_params(req_id, ticker, "", "STK", con_id)
        try:
            _, chain_params = ib_connector.wrapper.sec_def_opt_params_queue.get(timeout=10)
            if not chain_params:
                logger.error(f"Failed to fetch option chain for {ticker}, received empty params.")
                return None, None
            return chain_params.get("expirations"), chain_params.get("strikes")
        except Empty:
            logger.error(f"Timeout fetching option chain parameters for {ticker}.")
            return None, None

    def _filter_target_expiration(self, expirations: List[str]) -> Optional[str]:
        """Finds the closest expiration date based on config."""
        target_date = datetime.now() + timedelta(days=self.config.gex.days_to_expiration)
        
        min_delta = float('inf')
        target_expiration = None
        for exp_str in expirations:
            exp_date = datetime.strptime(exp_str, "%Y%m%d")
            delta = abs((exp_date - target_date).days)
            if delta < min_delta:
                min_delta = delta
                target_expiration = exp_str
        
        if not target_expiration:
            logger.error("Could not find a suitable expiration date.")
        return target_expiration

    def _filter_target_strikes(self, strikes: List[float], underlying_price: float) -> List[float]:
        """Filters strikes to a quantity around the underlying price."""
        strikes_quantity = self.config.gex.strikes_quantity
        
        # Find the strike closest to the current price
        closest_strike = min(strikes, key=lambda s: abs(s - underlying_price))
        closest_strike_index = strikes.index(closest_strike)

        # Get N strikes on either side
        start_index = max(0, closest_strike_index - strikes_quantity // 2)
        end_index = min(len(strikes), start_index + strikes_quantity)
        
        return strikes[start_index:end_index]

    def _build_option_contracts(self, ticker: str, expiration: str, strikes: List[float]) -> List[Contract]:
        """Builds a list of call and put Contract objects."""
        contracts = []
        for strike in strikes:
            for right in ["C", "P"]:
                contract = Contract()
                contract.symbol = ticker
                contract.secType = "OPT"
                contract.exchange = self.config.instrument.exchange
                contract.currency = self.config.instrument.currency
                contract.lastTradeDateOrContractMonth = expiration
                contract.strike = strike
                contract.right = right
                contract.multiplier = str(self.config.gex.option_multiplier)
                contracts.append(contract)
        return contracts

    def _request_market_data(self, ib_connector: "IBConnector", contracts: List[Contract]) -> Tuple[Dict, Dict]:
        """Requests snapshot data for a list of contracts."""
        req_id_map = {}
        # {req_id: {'gamma': None, 'oi': None, 'strike': float, 'right': 'C'|'P'}}
        data_aggregator = {}

        logger.info(f"Requesting market data for {len(contracts)} option contracts.")
        for contract in contracts:
            req_id = ib_connector.get_next_request_id()
            req_id_map[req_id] = {"strike": contract.strike, "right": contract.right}
            data_aggregator[req_id] = {"gamma": None, "oi": None}
            # Request greeks (104) and open interest (101)
            ib_connector.req_market_data(req_id, contract, "101,104", True, False)
        
        return req_id_map, data_aggregator

    def _collect_market_data(self, ib_connector: "IBConnector", num_requests: int, data_aggregator: Dict):
        """Collects data from queues with a timeout."""
        logger.info("Collecting market data from queues...")
        start_time = datetime.now()
        timeout_seconds = 20
        
        greeks_received = 0
        oi_received = 0

        while (greeks_received < num_requests or oi_received < num_requests):
            if (datetime.now() - start_time).seconds > timeout_seconds:
                logger.warning("Market data collection timed out.")
                break

            try:
                # Check for greeks
                greek_req_id, greek_data = ib_connector.wrapper.option_greeks_queue.get_nowait()
                if greek_req_id in data_aggregator and data_aggregator[greek_req_id]["gamma"] is None:
                    data_aggregator[greek_req_id]["gamma"] = greek_data.get("gamma")
                    greeks_received += 1
            except Empty:
                pass # Queue is empty, continue

            try:
                # Check for open interest (tick types 27 for Call, 28 for Put)
                oi_req_id, tick_type, size = ib_connector.wrapper.tick_size_queue.get_nowait()
                if oi_req_id in data_aggregator and data_aggregator[oi_req_id]["oi"] is None:
                     if tick_type in [27, 28]: # Call OI, Put OI
                        data_aggregator[oi_req_id]["oi"] = size
                        oi_received += 1
            except Empty:
                pass # Queue is empty, continue
        
        logger.info(f"Collected {greeks_received}/{num_requests} greeks and {oi_received}/{num_requests} OI values.")

    def _calculate_gex(self, req_id_map: Dict, data_aggregator: Dict) -> Dict[float, float]:
        """Calculates total GEX per strike."""
        gex_by_strike = defaultdict(float)
        multiplier = self.config.gex.option_multiplier

        for req_id, data in data_aggregator.items():
            gamma = data.get("gamma")
            oi = data.get("oi")
            
            if gamma is not None and oi is not None and gamma > -1 and oi > -1:
                strike_info = req_id_map[req_id]
                strike = strike_info["strike"]
                
                # Per the formula: GEX = gamma * open_interest * 100
                # The total GEX for a strike is the sum of GEX from calls and puts.
                gex = gamma * oi * multiplier
                gex_by_strike[strike] += gex
            else:
                strike_info = req_id_map.get(req_id, {"strike": "Unknown", "right": ""})
                logger.debug(f"Skipping GEX calc for ReqId {req_id} (Strike: {strike_info['strike']} {strike_info['right']}) due to missing data: Gamma={gamma}, OI={oi}")

        return dict(gex_by_strike)