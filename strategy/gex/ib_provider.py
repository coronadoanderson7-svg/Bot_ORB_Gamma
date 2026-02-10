# strategy/gex/ib_provider.py
import logging
import math
import time
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
    data directly from Interactive Brokers (IB) in controlled batches.
    """

    def __init__(self, config: AppConfig):
        """
        Initializes the IBProvider with the application's configuration.
        """
        super().__init__(config)
        if self.config.gex.batch_size == 20 and self.config.gex.batch_pause_seconds == 0.20:
            logger.warning(
                "Using default GEX batch settings (batch_size=20, batch_pause_seconds=0.20). "
                "It's recommended to set these in your config.yaml for optimal performance."
            )

    def get_max_gamma_strike(self, ticker: str, ib_connector: "IBConnector" = None) -> tuple[float, str, list[float]]:
        """
        Fetches option chain and market data from IB in sequential batches, 
        calculates GEX, and identifies the strike with the maximum gamma exposure.
        
        Returns:
            A tuple containing (max_gamma_strike, target_expiration, target_strikes_list).
        """
        if not ib_connector or not ib_connector.is_connected():
            logger.error("IBProvider cannot fetch data: IBConnector is not available or not connected.")
            return (0.0, "", [])

        try:
            logger.info("--- Starting GEX Analysis ---")
            # --- Setup Phase ---
            logger.info("Phase 1: Setup and Initial Data Fetch...")
            underlying_contract = self._create_underlying_contract(ticker)
            details = ib_connector.resolve_contract_details(underlying_contract)
            if not details:
                logger.error(f"GEX Pre-flight Check Failed: Could not resolve contract for {ticker}.")
                return (0.0, "", [])
            underlying_con_id = details.contract.conId

            underlying_price = self._fetch_underlying_price(ib_connector, underlying_contract)
            if not underlying_price:
                logger.error(f"GEX Pre-flight Check Failed: Could not fetch underlying price for {ticker}.")
                return (0.0, "", [])
            
            expirations, strikes = self._fetch_option_chain_params(ib_connector, ticker, underlying_con_id)
            if not expirations or not strikes:
                # Specific error is logged inside the function, no need to repeat here.
                return (0.0, "", [])

            target_expiration = self._filter_target_expiration(expirations)
            if not target_expiration:
                # Specific error is logged inside the function
                return (0.0, "", [])
            
            target_strikes = self._filter_target_strikes(strikes, underlying_price)

            # --- Batch Processing Phase ---
            logger.info("Phase 2: Batch Processing Option Contracts...")
            all_option_contracts = self._build_option_contracts(ticker, target_expiration, target_strikes)
            
            # Master aggregators for all batches
            master_req_id_map = {}
            master_data_aggregator = {}

            batch_size = self.config.gex.batch_size
            num_batches = math.ceil(len(all_option_contracts) / batch_size)
            logger.info(f"Preparing to process {len(all_option_contracts)} contracts in {num_batches} batches of size {batch_size}.")

            for i in range(num_batches):
                batch_num = i + 1
                logger.info(f"--- Processing GEX Batch {batch_num}/{num_batches} ---")
                
                batch_start_index = i * batch_size
                batch_end_index = batch_start_index + batch_size
                contract_batch = all_option_contracts[batch_start_index:batch_end_index]

                # 5a. Request streaming data for the current batch
                batch_req_id_map, batch_data_aggregator = self._request_market_data(ib_connector, contract_batch)
                if not batch_req_id_map:
                    logger.warning(f"Failed to request data for batch {batch_num}. Skipping.")
                    continue
                
                # 5b. Collect streaming data for the current batch
                self._collect_market_data(ib_connector, batch_req_id_map, batch_data_aggregator)
                
                # 5c. Cancel market data streams to free up data lines
                logger.debug(f"Cancelling {len(batch_req_id_map)} market data streams for batch {batch_num}.")
                for req_id in batch_req_id_map.keys():
                    ib_connector.cancel_market_data(req_id)

                # 5d. Merge batch results into master aggregators
                master_req_id_map.update(batch_req_id_map)
                master_data_aggregator.update(batch_data_aggregator)

                # 5e. Pause between batches
                if batch_num < num_batches:
                    logger.info(f"Pausing for {self.config.gex.batch_pause_seconds} second(s) before next batch.")
                    time.sleep(self.config.gex.batch_pause_seconds)

            # --- Final Calculation Phase ---
            logger.info("Phase 3: Final GEX Calculation...")
            if not master_data_aggregator:
                logger.error("GEX Analysis Failed: No data was collected after processing all batches.")
                return (0.0, "", [])

            gex_by_strike = self._calculate_gex(master_req_id_map, master_data_aggregator)
            if not gex_by_strike:
                logger.error("GEX Analysis Failed: GEX calculation resulted in no data, likely due to missing gamma or OI values.")
                return (0.0, "", [])
                
            max_gex_strike = max(gex_by_strike, key=gex_by_strike.get)
            logger.info(f"GEX Analysis Complete. Found max GEX strike: {max_gex_strike} with GEX value {gex_by_strike[max_gex_strike]:.2f}")

            return (max_gex_strike, target_expiration, target_strikes)

        except Exception as e:
            logger.exception(f"An unexpected error occurred during GEX calculation: {e}")
            return (0.0, "", [])

    def _create_underlying_contract(self, ticker: str) -> Contract:
        """Creates an ibapi.Contract for the underlying stock/index."""
        contract = Contract()
        contract.symbol = ticker
        contract.secType = "STK" if ticker.upper() not in ["SPX", "VIX"] else "IND"
        contract.exchange = self.config.instrument.exchange
        contract.currency = self.config.instrument.currency
        return contract

    def _fetch_underlying_price(self, ib_connector: "IBConnector", contract: Contract) -> Optional[float]:
        """
        Fetches the current price for a given contract from a snapshot.
        """
        logger.info(f"Fetching underlying price for {contract.symbol}...")
        req_id = ib_connector.get_next_request_id()
        ib_connector.req_market_data(req_id, contract, "", True, False) # Snapshot request
        
        ACCEPTABLE_TICK_TYPES = [4, 1, 2] # 4: Last, 1: Bid, 2: Ask

        try:
            while True:
                q_req_id, q_tick_type, q_price, _ = ib_connector.wrapper.tick_price_queue.get(timeout=10)
                if q_req_id == req_id and q_tick_type in ACCEPTABLE_TICK_TYPES:
                    logger.info(f"Underlying price for {contract.symbol} is {q_price} (using tick type {q_tick_type}).")
                    ib_connector.cancel_market_data(req_id)
                    return q_price
        except Empty:
            logger.error(f"Timeout fetching underlying price for {contract.symbol}. No valid price tick (1, 2, or 4) received in time.")
            return None

    def _fetch_option_chain_params(self, ib_connector: "IBConnector", ticker: str, con_id: int) -> Tuple[Optional[List[str]], Optional[List[float]]]:
        """Fetches all expirations and strikes for an underlying."""
        logger.info(f"Fetching option chain parameters for {ticker} (ConId: {con_id})...")
        req_id = ib_connector.get_next_request_id()
        sec_type = "STK" if ticker.upper() not in ["SPX", "VIX"] else "IND"
        ib_connector.req_sec_def_opt_params(req_id, ticker, "", sec_type, con_id)
        try:
            _, chain_params = ib_connector.wrapper.sec_def_opt_params_queue.get(timeout=10)
            if not chain_params or not chain_params.get("expirations") or not chain_params.get("strikes"):
                logger.error(f"Failed to fetch option chain for {ticker}. IB returned empty or incomplete parameters.")
                return None, None
            
            expirations = chain_params.get("expirations")
            strikes = chain_params.get("strikes")
            logger.info(f"Found {len(expirations)} expirations and {len(strikes)} strikes for {ticker}.")
            return expirations, strikes
        except Empty:
            logger.error(f"Timeout fetching option chain parameters for {ticker}. No response from IB.")
            return None, None

    def _filter_target_expiration(self, expirations: List[str]) -> Optional[str]:
        """Finds the closest expiration date based on config."""
        days_to_exp = self.config.gex.days_to_expiration
        logger.info(f"Filtering for expiration closest to {days_to_exp} day(s) from now...")
        target_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=days_to_exp)
        
        min_delta = float('inf')
        target_expiration = None
        for exp_str in expirations:
            exp_date = datetime.strptime(exp_str, "%Y%m%d")
            delta = abs((exp_date - target_date).days)
            if delta < min_delta:
                min_delta = delta
                target_expiration = exp_str
        
        if not target_expiration:
            logger.error(f"Could not find a suitable expiration date near {target_date.strftime('%Y-%m-%d')}.")
        else:
            logger.info(f"Target expiration selected: {target_expiration}")
        return target_expiration

    def _filter_target_strikes(self, strikes: List[float], underlying_price: float) -> List[float]:
        """Filters strikes to a quantity around the underlying price."""
        strikes_quantity = self.config.gex.strikes_quantity
        logger.info(f"Filtering for {strikes_quantity} strikes around underlying price {underlying_price}...")
        
        closest_strike = min(strikes, key=lambda s: abs(s - underlying_price))
        closest_strike_index = strikes.index(closest_strike)

        start_index = max(0, closest_strike_index - strikes_quantity // 2)
        end_index = min(len(strikes), start_index + strikes_quantity)
        
        filtered_strikes = strikes[start_index:end_index]
        logger.info(f"Target strikes selected. Range: {filtered_strikes[0]} to {filtered_strikes[-1]} ({len(filtered_strikes)} strikes).")
        return filtered_strikes

    def _build_option_contracts(self, ticker: str, expiration: str, strikes: List[float]) -> List[Contract]:
        """Builds a list of call and put Contract objects."""
        logger.info(f"Building {len(strikes) * 2} option contract objects...")
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
        """Requests streaming market data for a list of contracts."""
        req_id_map = {}
        data_aggregator = {}

        logger.info(f"Requesting streaming market data for {len(contracts)} option contracts.")
        for contract in contracts:
            req_id = ib_connector.get_next_request_id()
            req_id_map[req_id] = {"strike": contract.strike, "right": contract.right}
            data_aggregator[req_id] = {"gamma": None, "oi": None}
            # Request greeks (104) and open interest (101) via a streaming request
            ib_connector.req_market_data(req_id, contract, "101,104", False, False)
        
        return req_id_map, data_aggregator

    def _collect_market_data(self, ib_connector: "IBConnector", req_id_map: Dict, data_aggregator: Dict):
        """
        Collects streaming data from queues for a given batch. It waits until
        all requests have received both gamma and open interest, or a timeout occurs.
        """
        num_requests = len(req_id_map)
        logger.info(f"Collecting streaming data for {num_requests} requests...")
        start_time = datetime.now()
        
        # Use a configurable timeout. Default to 5 seconds for streaming, which is usually very fast.
        timeout_seconds = self.config.gex.batch_timeout_seconds if hasattr(self.config.gex, 'batch_timeout_seconds') else 5

        # A set of request IDs for which we are still waiting for data.
        pending_req_ids = set(req_id_map.keys())

        while pending_req_ids:
            # Check for overall timeout
            if (datetime.now() - start_time).seconds > timeout_seconds:
                logger.warning(
                    f"Batch data collection timed out after {timeout_seconds}s. "
                    f"{len(pending_req_ids)}/{num_requests} requests did not complete. GEX data will be partial."
                )
                # Log which requests are incomplete and what data is missing
                for req_id in list(pending_req_ids):
                    data = data_aggregator[req_id]
                    info = req_id_map[req_id]
                    logger.debug(f"Incomplete ReqId {req_id} ({info['strike']} {info['right']}): Gamma={data['gamma']}, OI={data['oi']}")
                break

            try:
                # Check for greeks from the queue (non-blocking)
                greek_req_id, greek_data = ib_connector.wrapper.option_greeks_queue.get_nowait()
                if greek_req_id in data_aggregator and data_aggregator[greek_req_id]["gamma"] is None:
                    gamma_val = greek_data.get("gamma")
                    # IB can send NaN for greeks, treat it as valid data to stop waiting
                    if gamma_val is not None:
                        data_aggregator[greek_req_id]["gamma"] = gamma_val
            except Empty:
                pass  # Queue is empty, continue

            try:
                # Check for open interest from the queue (non-blocking)
                oi_req_id, tick_type, size = ib_connector.wrapper.tick_size_queue.get_nowait()
                if oi_req_id in data_aggregator and data_aggregator[oi_req_id]["oi"] is None:
                    if tick_type in [27, 28]:  # Call OI, Put OI
                        data_aggregator[oi_req_id]["oi"] = size
            except Empty:
                pass  # Queue is empty, continue
            
            # Check for completed requests and remove them from the pending set
            completed_this_loop = set()
            for req_id in pending_req_ids:
                data = data_aggregator[req_id]
                if data["gamma"] is not None and data["oi"] is not None:
                    completed_this_loop.add(req_id)
                    logger.debug(f"Data collection complete for ReqId {req_id}.")
            
            if completed_this_loop:
                pending_req_ids.difference_update(completed_this_loop)
                logger.debug(f"{len(pending_req_ids)} requests remaining in batch.")

            # Small sleep to prevent CPU pegging if queues are constantly empty
            time.sleep(0.001)

        completed_count = num_requests - len(pending_req_ids)
        logger.info(
            f"Batch collection complete. {completed_count}/{num_requests} requests finished in "
            f"{(datetime.now() - start_time).total_seconds():.2f} seconds."
        )

    def _calculate_gex(self, req_id_map: Dict, data_aggregator: Dict) -> Dict[float, float]:
        """Calculates total GEX per strike from the aggregated data."""
        logger.info(f"Calculating GEX from {len(data_aggregator)} collected data points...")
        gex_by_strike = defaultdict(float)
        multiplier = self.config.gex.option_multiplier

        for req_id, data in data_aggregator.items():
            gamma = data.get("gamma")
            oi = data.get("oi")
            
            # Ensure data is valid before calculating
            if gamma is not None and oi is not None and gamma > -1 and oi > -1:
                strike_info = req_id_map[req_id]
                strike = strike_info["strike"]
                
                # Formula: GEX = gamma * open_interest * 100
                gex = gamma * oi * multiplier
                gex_by_strike[strike] += gex
            else:
                strike_info = req_id_map.get(req_id, {"strike": "Unknown", "right": ""})
                logger.debug(f"Skipping GEX calc for ReqId {req_id} (Strike: {strike_info['strike']} {strike_info['right']}) due to missing data: Gamma={gamma}, OI={oi}")

        return dict(gex_by_strike)