"""
Stage 3: Gamma Exposure (GEX) Analysis.

This module is responsible for identifying the strike with the largest gamma
magnitude to enhance trade selection.
"""
import logging
import time
from datetime import datetime, date, timedelta
from typing import Dict, Any, List, Optional, Tuple
from queue import Empty
from ibapi.contract import Contract

from core.logging_setup import logger
from ib_client.connector import IBConnector

class GEXAnalyzer:
    """
    Calculates Gamma Exposure (GEX) for a given underlying instrument.
    """

    def __init__(self, connector: IBConnector, config: Dict[str, Any]):
        """
        Initializes the GEXAnalyzer.

        Args:
            connector: An initialized and connected IBConnector instance.
            config: The application configuration dictionary.
        """
        self.logger = logging.getLogger(__name__)
        self.ib_connector = connector
        
        gex_config = config.get("gex", {})
        self.days_to_expiration = gex_config.get("days_to_expiration", 0)
        self.strikes_quantity = gex_config.get("strikes_quantity", 120)
        self.option_multiplier = gex_config.get("option_multiplier", 100)
        
        self.instrument_config = config.get("instrument", {})
        self.underlying_symbol = self.instrument_config.get("ticker", "SPX")

        self.next_req_id = 1000  # Starting reqId high to avoid conflicts
        
        self.logger.info("GEXAnalyzer initialized.")

    def get_next_req_id(self) -> int:
        """Generates a unique request ID for this module."""
        self.next_req_id += 1
        return self.next_req_id

    def find_and_calculate_gex(self) -> Optional[Tuple[float, str]]:
        """
        The main public method to orchestrate the entire GEX calculation process.
        
        Returns:
            A tuple containing (highest_gex_strike, target_expiration), or None if calculation fails.
        """
        self.logger.info("Starting GEX calculation process...")

        # Step 1: Resolve the underlying contract to get its conId
        underlying_contract = self._create_underlying_contract()
        details = self.ib_connector.resolve_contract_details(underlying_contract)
        
        if not (details and details.contract and details.contract.conId):
            self.logger.error(f"Failed to resolve contract for {self.underlying_symbol}. Aborting GEX.")
            return None
        
        underlying_con_id = details.contract.conId
        # Use the market name from the resolved contract for better option chain accuracy
        self.underlying_exchange = details.marketName
        
        # Step 2: Request option parameters to find expirations and strikes
        expirations, strikes = self._get_option_parameters(underlying_con_id)
        if not expirations or not strikes:
            self.logger.error("Failed to retrieve option parameters. Aborting GEX.")
            return None

        # Step 3: Find the target expiration date
        target_expiration = self._find_target_expiration(expirations)
        if not target_expiration:
            self.logger.error(f"No suitable expiration found for DTE={self.days_to_expiration}. Aborting GEX.")
            return None
        self.logger.info(f"Target expiration date found: {target_expiration}")

        # Step 4: Get the current underlying price to find ATM strikes
        spot_price = self._get_underlying_spot_price(underlying_contract)
        if spot_price is None:
            self.logger.error("Failed to fetch spot price for the underlying. Aborting GEX.")
            return None
        self.logger.info(f"Successfully fetched spot price: {spot_price}")

        # Step 5: Filter strikes around the ATM price
        atm_strikes = self._filter_strikes(strikes, spot_price)
        self.logger.info(f"Found {len(atm_strikes)} strikes to analyze around {spot_price}.")

        # Step 6, 7, 8: Calculate GEX for each strike
        gex_per_strike = self._calculate_gex_for_strikes(target_expiration, atm_strikes)
        if not gex_per_strike:
            self.logger.error("Failed to calculate GEX for any strikes.")
            return None
            
        # Step 9: Find the strike with the highest absolute GEX
        highest_gex_strike = max(gex_per_strike, key=lambda k: abs(gex_per_strike[k]))
        
        self.logger.info(f"GEX Calculation Complete. Highest GEX Strike: {highest_gex_strike} (GEX: {gex_per_strike[highest_gex_strike]:.2f})")
        
        return highest_gex_strike, target_expiration

    def _get_underlying_spot_price(self, contract: Contract) -> Optional[float]:
        """
        Requests and retrieves the last traded price for the underlying contract.
        """
        req_id = self.get_next_req_id()
        self.logger.info(f"Requesting spot price for {contract.symbol} (ReqId: {req_id})...")
        
        # Request market data with a snapshot. Generic tick list "4" is for Last Price.
        self.ib_connector.req_market_data(req_id, contract, "4", True, False)

        try:
            start_time = time.time()
            while time.time() - start_time < 10: # 10-second timeout
                try:
                    # Non-blocking get from the queue
                    q_req_id, tick_type, price, _ = self.ib_connector.wrapper.tick_price_queue.get_nowait()
                    
                    if q_req_id == req_id:
                        # TickType 4 is Last Price
                        if tick_type == 4:
                            self.logger.info(f"Received spot price: {price} for ReqId: {req_id}")
                            return price
                        # TickType 9 is Close Price, a fallback if last price isn't available
                        elif tick_type == 9:
                            self.logger.warning(f"Last price not available, using close price: {price}")
                            return price

                except Empty:
                    time.sleep(0.1) # Wait briefly before trying again
            
            self.logger.error(f"Timeout waiting for spot price for ReqId: {req_id}")
            return None

        except Exception as e:
            self.logger.exception(f"Error fetching spot price: {e}")
            return None
        finally:
            # Always cancel the market data request
            self.ib_connector.cancel_market_data(req_id)

    def _create_underlying_contract(self) -> Contract:
        """Creates the contract object for the underlying security."""
        contract = Contract()
        contract.symbol = self.instrument_config.get("ticker")
        contract.secType = "IND" if contract.symbol == "SPX" else "STK"
        contract.exchange = self.instrument_config.get("exchange")
        contract.currency = self.instrument_config.get("currency")
        return contract

    def _get_option_parameters(self, underlying_con_id: int) -> Tuple[Optional[List[str]], Optional[List[float]]]:
        """
        ReqSecDefOptParams: Requests available expirations and strikes for the underlying.
        """
        req_id = self.get_next_req_id()
        self.logger.info(f"Requesting option parameters for conId {underlying_con_id} (ReqId: {req_id})...")
        
        self.ib_connector.req_sec_def_opt_params(
            req_id, 
            self.underlying_symbol, 
            "", # Exchange is empty for IND
            "IND", 
            underlying_con_id
        )

        try:
            # We expect multiple responses for different exchanges, we take the first valid one.
            all_expirations = set()
            all_strikes = set()
            while True:
                params = self.ib_connector.wrapper.sec_def_opt_params_queue.get(timeout=20)
                if params[0] == req_id and params[1] is None: # End of stream for this reqId
                    break
                
                # Unpack the data: reqId, exchange, underlyingConId, tradingClass, multiplier, expirations, strikes
                _, _, _, _, _, expirations, strikes = params
                all_expirations.update(expirations)
                all_strikes.update(strikes)

            if not all_strikes:
                self.logger.warning("No strikes received from option parameters request.")
                return None, None

            return sorted(list(all_expirations)), sorted(list(all_strikes))

        except Exception as e:
            self.logger.exception(f"Error fetching option parameters: {e}")
            return None, None
            
    def _find_target_expiration(self, expirations: List[str]) -> Optional[str]:
        """
        Finds the expiration date that matches the `days_to_expiration` setting.
        """
        today = date.today()
        target_date = today + timedelta(days=self.days_to_expiration)
        
        for exp_str in expirations:
            exp_date = datetime.strptime(exp_str, "%Y%m%d").date()
            if exp_date == target_date:
                return exp_str
        return None

    def _filter_strikes(self, strikes: List[float], spot_price: float) -> List[float]:
        """
        Filters the full list of strikes to a manageable quantity around the spot price.
        """
        # Find the index of the strike closest to the spot price
        closest_strike_index = min(range(len(strikes)), key=lambda i: abs(strikes[i] - spot_price))
        
        # Calculate the start and end indices for the desired quantity
        half_quantity = self.strikes_quantity // 2
        start_index = max(0, closest_strike_index - half_quantity)
        end_index = min(len(strikes), closest_strike_index + half_quantity)
        
        return strikes[start_index:end_index]

    def _calculate_gex_for_strikes(self, expiration: str, strikes: List[float]) -> Dict[float, float]:
        """
        Subscribes to market data for options and calculates GEX for each strike.
        """
        gex_results = {}
        # This is a very complex process. A robust implementation would use a manager
        # to handle the flood of reqMktData requests and responses.
        # This simplified version does it sequentially, which is slow.
        for strike in strikes:
            self.logger.debug(f"Calculating GEX for strike: {strike}")
            # Step 1: Create Call and Put contracts
            call_contract = self._create_option_contract(expiration, strike, "C")
            put_contract = self._create_option_contract(expiration, strike, "P")

            # Step 2: Request market data
            call_req_id = self.get_next_req_id()
            put_req_id = self.get_next_req_id()
            
            # Requesting Greeks (tick 101) and Open Interest (tick 100)
            self.ib_connector.req_market_data(call_req_id, call_contract, "100,101", True, False)
            self.ib_connector.req_market_data(put_req_id, put_contract, "100,101", True, False)

            # Step 3: Fetch results from queues
            try:
                call_gamma, call_oi = self._get_option_data(call_req_id)
                put_gamma, put_oi = self._get_option_data(put_req_id)
                
                # Step 4: Calculate GEX for this strike
                call_gex = call_gamma * call_oi * self.option_multiplier if call_gamma and call_oi else 0
                put_gex = put_gamma * put_oi * self.option_multiplier if put_gamma and put_oi else 0
                
                total_gex = call_gex - put_gex # Puts are negative
                gex_results[strike] = total_gex
                self.logger.debug(f"Strike: {strike} | Call GEX: {call_gex:.0f} | Put GEX: {-put_gex:.0f} | Total: {total_gex:.0f}")

            except Exception as e:
                self.logger.warning(f"Could not calculate GEX for strike {strike}: {e}")
            finally:
                # Step 5: Clean up subscriptions
                self.ib_connector.cancel_market_data(call_req_id)
                self.ib_connector.cancel_market_data(put_req_id)

        return gex_results

    def _get_option_data(self, req_id: int) -> Tuple[Optional[float], Optional[int]]:
        """
        Retrieves Gamma and Open Interest from the wrapper queues for a given request.
        This is a blocking operation with a timeout.
        """
        gamma, open_interest = None, None
        
        # This logic is complex because ticks can arrive in any order.
        # A more robust solution would use a dedicated data handler class.
        start_time = time.time()
        while time.time() - start_time < 10: # 10 second timeout per strike
            # Check for Gamma (from tickOptionComputation)
            if not self.ib_connector.wrapper.option_computation_queue.empty():
                comp_req_id, data = self.ib_connector.wrapper.option_computation_queue.get_nowait()
                if comp_req_id == req_id:
                    gamma = data.get("gamma")

            # Check for Open Interest (from tickSize)
            if not self.ib_connector.wrapper.tick_size_queue.empty():
                size_req_id, tick_type, size = self.ib_connector.wrapper.tick_size_queue.get_nowait()
                # TickType 27 corresponds to Option Open Interest
                if size_req_id == req_id and tick_type == 27:
                    open_interest = size
            
            if gamma is not None and open_interest is not None:
                return gamma, open_interest
        
        raise TimeoutError("Timed out waiting for full option data (Gamma, OI).")

    def _create_option_contract(self, expiration: str, strike: float, right: str) -> Contract:
        """Helper to create an option contract."""
        contract = Contract()
        contract.symbol = self.underlying_symbol
        contract.secType = "OPT"
        contract.exchange = self.instrument_config.get("exchange")
        contract.currency = self.instrument_config.get("currency")
        contract.lastTradeDateOrContractMonth = expiration
        contract.strike = strike
        contract.right = right
        contract.multiplier = str(self.option_multiplier)
        return contract
