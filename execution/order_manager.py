# execution/order_manager.py

import logging
import math
import time
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_EVEN
import queue
from ibapi.contract import Contract
from ibapi.order import Order
from typing import Optional, Tuple

from ib_client.connector import IBConnector
from models.data_models import SignalType
from core.config_loader import APP_CONFIG

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class OrderManager:
    """
    Manages the creation, submission, and tracking of trades based on trading signals.
    """

    def __init__(self, ib_connector: IBConnector):
        """
        Initializes the OrderManager.

        :param ib_connector: An instance of the IBConnector to interact with TWS/Gateway.
        """
        self.ib_connector = ib_connector
        self.contract_info = APP_CONFIG.instrument
        self.trade_management = APP_CONFIG.trade_management
        self.order_defaults = APP_CONFIG.trade_execution.order_defaults
        self.total_quantity = APP_CONFIG.trade_execution.total_quantity
        self.active_positions = {} # parent_order_id -> {stop_loss_order_id, take_profit_order_id, contract, min_tick}
        
    def _make_trade_decision(self, signal_type: SignalType, spot_price: float, strike_price: float) -> Optional[str]:
        """
        Determines the option type ('C' for Call, 'P' for Put) based on the 4-condition table.

        :param signal_type: The type of signal (BUY or SELL).
        :param spot_price: Current market price of the underlying.
        :param strike_price: The key strike price from GEX analysis.
        :return: 'C' for Call, 'P' for Put, or None if no trade.
        """
        is_bullish_signal = (signal_type == SignalType.BUY)
        gex_is_above_spot = (strike_price > spot_price)

        if is_bullish_signal and gex_is_above_spot:
            logger.info("Decision: Bullish signal and GEX above spot -> BUY CALL.")
            return 'C'
        elif is_bullish_signal and not gex_is_above_spot:
            logger.info("Decision: Bullish signal and GEX below spot -> BUY PUT.")
            return 'P'
        elif not is_bullish_signal and gex_is_above_spot:
            logger.info("Decision: Bearish signal and GEX above spot -> BUY CALL.")
            return 'C'
        elif not is_bullish_signal and not gex_is_above_spot:
            logger.info("Decision: Bearish signal and GEX below spot -> BUY PUT.")
            return 'P'
        
        return None

    def _get_atm_strike(self, spot_price: float, strike_list: list) -> Optional[float]:
        """
        Finds the At-The-Money (ATM) strike closest to the current spot price from a list.
        """
        if not strike_list:
            logger.error("Strike list is empty. Cannot determine ATM strike.")
            return None
            
        return min(strike_list, key=lambda x: abs(x - spot_price))

    def _create_option_contract(self, symbol: str, atm_strike: float, option_type: str, expiration_date: str) -> Contract:
        """
        Creates and configures an ibapi.contract.Contract object for an option.

        :param symbol: The underlying ticker symbol.
        :param atm_strike: The selected strike price for the option.
        :param option_type: 'C' for Call or 'P' for Put.
        :param expiration_date: The contract expiration date in YYYYMMDD format.
        :return: A fully populated Contract object.
        """
        contract = Contract()
        contract.symbol = symbol
        contract.secType = "OPT"
        contract.exchange = self.contract_info.exchange
        contract.currency = self.contract_info.currency
        contract.lastTradeDateOrContractMonth = expiration_date
        contract.strike = atm_strike
        contract.right = option_type
        contract.multiplier = "100" # Standard for SPX options
        logger.info(f"Created contract: {symbol} {expiration_date} {atm_strike} {option_type}")
        return contract

    def _fetch_option_price(self, contract: Contract) -> Optional[float]:
        """
        Fetches the current market price for a given option contract.
        """
        logger.info(f"Fetching market price for {contract.localSymbol}...")
        market_data = self.ib_connector.fetch_market_price(contract)
        logger.info(f"Market data received: {market_data}")
        
        if not market_data:
            logger.error(f"Failed to fetch market price for {contract.localSymbol}.")
            return None

        # Prioritize which price to use. Since we are placing a BUY order,
        # the 'ask' price is the most relevant.
        price = market_data.get('ask')
        if price is None or price == -1: # IB uses -1 for unavailable data
            logger.warning(f"'ask' price not available for {contract.localSymbol}. Falling back.")
            price = market_data.get('last')
        if price is None or price == -1:
            logger.warning(f"'last' price not available for {contract.localSymbol}. Falling back to close.")
            price = market_data.get('close') 

        if price and price > 0:
             logger.info(f"Using price {price} for {contract.localSymbol}.")
             return price
        else:
            logger.error(f"Could not determine a valid price for {contract.localSymbol} from market data: {market_data}")
            return None

    def _place_opening_order(self, contract: Contract, price: float):
        """
        Prepares and places the opening order for a trade without transmitting subsequent bracket orders.

        :param contract: The option contract to trade.
        :param price: The limit price for the entry order.
        """
        if self.next_order_id is None:
            self.next_order_id = self.ib_connector.get_next_order_id()
            if self.next_order_id is None:
                logger.error("Failed to retrieve a valid next order ID. Aborting order placement.")
                return

        # For now, we only place the opening order. Bracket orders will be handled later.
        opening_order = Order()
        opening_order.orderId = self.next_order_id
        opening_order.action = "BUY" # We are always buying calls or puts
        opening_order.orderType = self.order_defaults.entry_order_type
        opening_order.lmtPrice = price
        opening_order.totalQuantity = self.total_quantity
        opening_order.eTradeOnly = False
        opening_order.firmQuoteOnly = False
        opening_order.transmit = False # Set to False to manage bracket orders manually

        logger.info(f"Preparing opening order ID {opening_order.orderId} for {contract.symbol} {contract.right} @ {price}")

        # Store the order details for later processing (e.g., adding bracket orders)
        # self.active_orders[opening_order.orderId] = {'contract': contract, 'order': opening_order}

        # self.ib_connector.place_order(opening_order.orderId, contract, opening_order)

        # Increment for the next set of orders
        self.next_order_id += 3 # Assuming a bracket order will follow

    def _create_bracket_orders(self, parent_order_id: int, tp_order_id: int, sl_order_id: int, entry_price: float, quantity: float, action: str, min_tick: float) -> Optional[Tuple[Order, Order]]:
        """
        Creates a take-profit and a stop-loss order based on the parent fill.

        Args:
            parent_order_id: The ID of the filled parent order.
            tp_order_id: The ID to use for the take-profit order.
            sl_order_id: The ID to use for the stop-loss order.
            entry_price: The entry price (limit price of parent) to calculate TP/SL from.
            quantity: The quantity of the parent order.
            action: The action of the parent order (e.g., "BUY").
            min_tick: The minimum tick size for price rounding.

        Returns:
            A tuple containing the (take_profit_order, stop_loss_order), or None if creation fails.
        """
        if action != "BUY":
            logger.error(f"Bracket orders are currently only supported for opening BUY orders. Got '{action}'. Cannot proceed.")
            return None

        # Calculate raw prices based on percentages from config
        tp_price_raw = entry_price * (1 + self.trade_management.take_profit_pct / 100)
        sl_price_raw = entry_price * (1 - self.trade_management.stop_loss_pct / 100)

        # Determine the correct tick size for EACH price level, as it is price-dependent.
        # This is the fix for the rounding error where a single tick size was used for both.
        tp_tick_size = self._get_spx_tick_size(tp_price_raw)
        sl_tick_size = self._get_spx_tick_size(sl_price_raw)

        # Sanitize prices using their respective, correct tick sizes.
        tp_price_sanitized = self._round_down_to_tick(tp_price_raw, tp_tick_size)
        sl_price_sanitized = self._round_down_to_tick(sl_price_raw, sl_tick_size)

        logger.info(f"Calculated bracket prices for parent {parent_order_id}: "
                    f"TP_raw={tp_price_raw:.4f}, TP_tick={tp_tick_size}, TP_sanitized={tp_price_sanitized:.2f} | "
                    f"SL_raw={sl_price_raw:.4f}, SL_tick={sl_tick_size}, SL_sanitized={sl_price_sanitized:.2f}")

        # Safety check: ensure stop loss isn't higher than entry for a long position.
        # If it is, it indicates a very small stop loss percentage; adjust down by one tick.
        if sl_price_sanitized >= entry_price:
            logger.warning(f"Calculated SL price ({sl_price_sanitized}) is at or above entry price ({entry_price}). Adjusting SL down by one tick.")
            # Use the stop-loss specific tick size for the adjustment
            sl_price_sanitized -= sl_tick_size
        
        # The closing action for a long position is always "SELL"
        closing_action = "SELL"

        # --- Create Take Profit Order ---
        take_profit_order = Order()
        take_profit_order.orderId = tp_order_id
        take_profit_order.parentId = parent_order_id
        take_profit_order.action = closing_action
        take_profit_order.orderType = "LMT"  # Limit order to lock in profit
        take_profit_order.lmtPrice = tp_price_sanitized
        take_profit_order.totalQuantity = quantity
        take_profit_order.tif = "GTC"  # Good-Til-Canceled for protective orders
        take_profit_order.transmit = False  # Do not transmit yet, part of a group
        take_profit_order.eTradeOnly = False
        take_profit_order.firmQuoteOnly = False

        # --- Create Stop Loss Order ---
        stop_loss_order = Order()
        stop_loss_order.orderId = sl_order_id
        stop_loss_order.parentId = parent_order_id
        stop_loss_order.action = closing_action
        stop_loss_order.orderType = "STP"  # Stop order to limit loss
        stop_loss_order.auxPrice = sl_price_sanitized
        stop_loss_order.totalQuantity = quantity
        stop_loss_order.tif = "GTC"  # Good-Til-Canceled for protective orders
        stop_loss_order.transmit = True  # Transmit the entire group with this last order
        stop_loss_order.eTradeOnly = False
        stop_loss_order.firmQuoteOnly = False

        return take_profit_order, stop_loss_order

    def _get_spx_tick_size(self, price: float) -> float:
        """
        Returns the standard tick size for SPX options based on the price level.
        - $0.05 for premiums below $3.00
        - $0.10 for premiums at or above $3.00
        """
        if price < 3.0:
            return 0.05
        return 0.10

    def place_trade(self, signal_type: SignalType, spot_price: float, strike_price: float, expiration_date: str, strike_list: list):
        """
        Creates and submits an atomic three-part bracket order (parent, take-profit,
        and stop-loss) in a single transaction.
        """
        logger.info(f"Processing trade signal: {signal_type} at spot price {spot_price} with strike {strike_price}")

        # 1. Make Trade Decision
        option_type = self._make_trade_decision(signal_type, spot_price, strike_price)
        if not option_type:
            logger.info("Trade decision resulted in no action. Exiting.")
            return

        # 2. Get ATM Strike
        atm_strike = self._get_atm_strike(spot_price, strike_list)
        if not atm_strike:
            logger.warning("Could not determine ATM strike from the fetched option chain. Aborting trade.")
            return

        # 3. Create a temporary contract to be resolved
        temp_contract = self._create_option_contract(
            symbol=self.contract_info.ticker,
            atm_strike=atm_strike,
            option_type=option_type,
            expiration_date=expiration_date
        )

        # 4. Resolve the contract to get its definitive details, including the conId.
        contract_details = self.ib_connector.resolve_contract_details(temp_contract)
        if not contract_details:
            logger.error(f"Could not resolve contract details for {temp_contract.localSymbol}. Aborting.")
            return
        
        # This is the key step: use the contract object returned within the details.
        # This object contains the unique conId.
        resolved_contract = contract_details.contract
        min_tick = contract_details.minTick
        logger.info(f"Successfully resolved contract. ConId: {resolved_contract.conId}, MinTick: {min_tick}")

        # 5. Fetch Option Price using the *resolved* contract
        option_price = self._fetch_option_price(resolved_contract)
        if not option_price:
            logger.error(f"Could not fetch market price for resolved contract {resolved_contract.conId}. Aborting.")
            return

        # Determine the correct tick size for the entry order. Fallback to rules if API minTick is invalid.
        entry_tick_size = min_tick if min_tick > 0 else self._get_spx_tick_size(option_price)
        logger.info(f"Using entry tick size of {entry_tick_size} for entry price {option_price}.")

        # 6. Get Order IDs for the entire bracket
        parent_order_id = self.ib_connector.get_next_request_id(count=3)
        tp_order_id = parent_order_id + 1
        sl_order_id = parent_order_id + 2

        # 7. Create Parent Order
        parent_order = Order()
        parent_order.orderId = parent_order_id
        parent_order.action = "BUY"
        parent_order.orderType = self.order_defaults.entry_order_type
        parent_order.lmtPrice = self._round_to_tick_size(option_price, entry_tick_size) # Use fetched price for limit
        parent_order.totalQuantity = self.total_quantity
        parent_order.tif = "DAY"
        parent_order.transmit = False # DO NOT transmit parent alone
        parent_order.eTradeOnly = False
        parent_order.firmQuoteOnly = False

        # 8. Create Bracket Orders
        bracket = self._create_bracket_orders(
            parent_order_id=parent_order_id,
            tp_order_id=tp_order_id,
            sl_order_id=sl_order_id,
            entry_price=parent_order.lmtPrice, # Base calculations on the parent's limit price
            quantity=parent_order.totalQuantity,
            action=parent_order.action,
            min_tick=entry_tick_size
        )

        if not bracket:
            logger.error("Failed to create bracket orders. Aborting trade.")
            return

        take_profit_order, stop_loss_order = bracket

        # 9. Place all three orders atomically
        logger.info(f"Submitting atomic bracket order group: Parent={parent_order_id}, TP={tp_order_id}, SL={sl_order_id}")
        self.ib_connector.place_order(resolved_contract, parent_order)
        self.ib_connector.place_order(resolved_contract, take_profit_order)
        self.ib_connector.place_order(resolved_contract, stop_loss_order) # This one transmits the group

        # 10. Register the position as active for management
        self.active_positions[parent_order_id] = {
            "stop_loss_order_id": sl_order_id,
            "take_profit_order_id": tp_order_id,
            "contract": resolved_contract,
            "min_tick": entry_tick_size, # Use the validated tick size
            "stop_loss_price": stop_loss_order.auxPrice, # Store the initial stop price
            "last_milestone_level": 0 # Initialize milestone tracking for this position
        }
        logger.info(f"Position for parent order {parent_order_id} is now active and being managed.")

    def _check_for_updates(self):
        """
        Checks the order status queue for fills or cancellations of bracket orders
        to determine if a position has been closed, then cleans up tracking.
        """
        try:
            while not self.ib_connector.get_order_status_queue().empty():
                status_update = self.ib_connector.get_order_status_queue().get_nowait()
                order_id = status_update['orderId']
                status = status_update['status']

                # Case 1: The parent order just got filled. Store its fill price.
                if order_id in self.active_positions and status == 'Filled':
                    # Check if it's a parent order that we haven't recorded the fill price for yet
                    if 'avg_cost' not in self.active_positions[order_id]:
                        avg_cost = status_update['avgFillPrice']
                        if avg_cost > 0:
                            self.active_positions[order_id]['avg_cost'] = avg_cost
                            logger.info(f"Parent order {order_id} filled at average cost {avg_cost}. Position is now fully active for management.")
                        else:
                            logger.warning(f"Parent order {order_id} filled but avgFillPrice is {avg_cost}. Cannot manage position.")
                        continue # Continue to next message in queue

                # Case 2: A child order was filled/cancelled, which means the position is closed.
                # Find which parent position this child order belongs to.
                terminal_states = {'Filled', 'Cancelled', 'ApiCancelled', 'Inactive'}
                parent_to_remove = None
                for parent_id, pos_data in self.active_positions.items():
                    # Check if the update is for a child order of an active position
                    if order_id in [pos_data['stop_loss_order_id'], pos_data['take_profit_order_id']]:
                        # AND check if the status is terminal
                        if status in terminal_states:
                            logger.info(
                                f"Detected position closure for parent order {parent_id}. "
                                f"Child order {order_id} has a terminal status: {status}."
                            )
                            parent_to_remove = parent_id
                            break
                        else:
                            # Log non-terminal updates for debugging but don't act on them.
                            logger.debug(f"Received non-terminal status '{status}' for child order {order_id}. No action taken.")
                
                if parent_to_remove:
                    del self.active_positions[parent_to_remove]
                    logger.info(f"Position for parent order {parent_to_remove} has been closed and removed from active management.")

        except queue.Empty:
            pass # This is a normal condition, means no new status updates.

    def manage_open_positions(self):
        """
        Periodically called by the engine to manage trailing stops for open positions.
        This method is now event-driven and does not poll for positions.
        """
        # First, process any status updates from the queue. This will update the
        # state of our tracked positions (e.g., record fill price, remove closed positions).
        self._check_for_updates()

        if not self.active_positions:
            return

        # Iterate over a copy of the items to allow for safe dictionary changes if a position is closed.
        for parent_id, pos_data in list(self.active_positions.items()):
            contract = pos_data.get("contract")
            avg_cost = pos_data.get("avg_cost")

            # If avg_cost is not yet set, it means the parent order hasn't been filled. Skip.
            if not contract or not avg_cost:
                continue

            # Fetch the current price for this specific active contract
            current_price = self._fetch_option_price(contract)
            if not current_price:
                logger.warning(f"Could not fetch price for active position {contract.localSymbol}, cannot manage trail.")
                continue

            # --- Milestone-based Trailing Stop Logic ---
            profit_pct = (current_price / avg_cost - 1) * 100.0  # As a percentage, e.g., 15.5
            activation_pct = self.trade_management.trailing_stop.activation_profit_pct
            last_milestone_level = pos_data.get("last_milestone_level", 0)

            # Ensure we don't divide by zero if activation_pct is not set
            if profit_pct >= activation_pct and activation_pct > 0:
                # Determine which profit milestone we are currently at (e.g., 1 for 10-19%, 2 for 20-29%)
                current_milestone_level = math.floor(profit_pct / activation_pct)

                # Only trigger an update if we have crossed a *new* milestone
                if current_milestone_level > last_milestone_level:
                    logger.info(
                        f"Profit at {profit_pct:.2f}% has crossed a new milestone "
                        f"(Level {current_milestone_level}). Checking for stop loss adjustment."
                    )
                    self._modify_stop_loss(parent_id, avg_cost, current_milestone_level)

    def _modify_stop_loss(self, parent_order_id: int, avg_cost: float, milestone_level: int):
        """
        Modifies the stop-loss order based on a milestone-based risk reduction strategy.
        Each time a profit milestone is crossed, the initial risk is reduced by a
        fixed percentage ('trail_pct').
        """
        position_data = self.active_positions.get(parent_order_id)
        if not position_data:
            return

        stop_loss_order_id = position_data["stop_loss_order_id"]
        contract = position_data["contract"]
        min_tick = position_data["min_tick"]
        current_stop_price = position_data["stop_loss_price"]

        # --- NEW LOGIC: Milestone-based Risk Reduction ---
        initial_stop_loss_pct = self.trade_management.stop_loss_pct
        trail_pct_per_milestone = self.trade_management.trailing_stop.trail_pct

        # 1. Calculate total risk reduction based on how many milestones have been passed.
        total_risk_reduction = milestone_level * trail_pct_per_milestone

        # 2. Calculate the new target risk percentage.
        new_risk_pct = initial_stop_loss_pct - total_risk_reduction

        # 3. Calculate the new stop price based on the *entry price* (avg_cost).
        new_stop_price_raw = avg_cost * (1 - new_risk_pct / 100.0)

        # 4. Sanitize the price by rounding it down to the nearest valid tick.
        new_stop_price_sanitized = self._round_down_to_tick(
            new_stop_price_raw,
            min_tick
        )

        # Only proceed if the newly calculated stop price is an improvement.
        if new_stop_price_sanitized > current_stop_price:
            logger.info(
                f"Milestone Stop (Level {milestone_level}): "
                f"New stop price {new_stop_price_sanitized} is higher than current {current_stop_price}. Submitting modification."
            )

            # Create a new order object with the SAME orderId to modify it
            modified_stop_order = Order()
            modified_stop_order.orderId = stop_loss_order_id
            modified_stop_order.action = "SELL"
            modified_stop_order.orderType = "STP"
            modified_stop_order.auxPrice = new_stop_price_sanitized
            modified_stop_order.totalQuantity = self.total_quantity
            modified_stop_order.tif = "GTC"
            modified_stop_order.transmit = True
            modified_stop_order.eTradeOnly = False
            modified_stop_order.firmQuoteOnly = False

            # Place the order to modify the existing one
            self.ib_connector.place_order(contract, modified_stop_order)
            
            # Update the stored price AND the milestone level to the new baseline
            self.active_positions[parent_order_id]["stop_loss_price"] = new_stop_price_sanitized
            self.active_positions[parent_order_id]["last_milestone_level"] = milestone_level
            logger.info(f"Successfully submitted modification for SL Order {stop_loss_order_id} to new price {new_stop_price_sanitized}.")

    def has_active_positions(self) -> bool:
        """
        Checks if there are any active positions being tracked or trades pending fill.
        """
        return bool(self.active_positions)

    def _round_to_tick_size(self, price: float, tick_size: float) -> float:
        """
        Rounds a price to the nearest valid tick size.
        This version uses the Decimal module for superior precision over float arithmetic.
        """
        if tick_size is None or tick_size <= 0:
            return round(price, 2)  # Default rounding if tick size is invalid

        price_d = Decimal(str(price))
        tick_d = Decimal(str(tick_size))

        # ROUND_HALF_EVEN is the standard for rounding to nearest (e.g., Python's round()).
        num_ticks = (price_d / tick_d).to_integral_value(rounding=ROUND_HALF_EVEN)
        rounded_price = num_ticks * tick_d

        return float(rounded_price)

    def _round_down_to_tick(self, price: float, tick_size: float) -> float:
        """
        Always rounds a price DOWN to the nearest valid tick size using the Decimal module for precision.
        """
        if tick_size is None or tick_size <= 0:
            return round(price, 2)  # Default rounding if tick size is invalid

        price_d = Decimal(str(price))
        tick_d = Decimal(str(tick_size))

        num_ticks = (price_d / tick_d).to_integral_value(rounding=ROUND_DOWN)
        rounded_price = num_ticks * tick_d

        return float(rounded_price)
