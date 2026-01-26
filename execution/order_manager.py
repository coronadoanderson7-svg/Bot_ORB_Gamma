# execution/order_manager.py

import logging
import time
from ibapi.contract import Contract
from ibapi.order import Order
from typing import Optional

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
        self.next_order_id = None # Should be initialized by fetching from IB client
        self.active_positions = {} # To store parent_order_id -> stop_loss_order_id

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
        opening_order.totalQuantity = 1
        opening_order.transmit = False # Set to False to manage bracket orders manually

        logger.info(f"Preparing opening order ID {opening_order.orderId} for {contract.symbol} {contract.right} @ {price}")

        # Store the order details for later processing (e.g., adding bracket orders)
        # self.active_orders[opening_order.orderId] = {'contract': contract, 'order': opening_order}

        # self.ib_connector.place_order(opening_order.orderId, contract, opening_order)

        # Increment for the next set of orders
        self.next_order_id += 3 # Assuming a bracket order will follow

    def _create_bracket_orders(self, parent_order_id: int, open_execution_price: float, action: str) -> tuple:
        """
        Creates a take profit and a stop loss order to form a bracket order.

        :param parent_order_id: The ID of the parent order.
        :param open_execution_price: The execution price of the parent order.
        :param action: The action of the parent order ("BUY" or "SELL").
        :return: A tuple containing the (take_profit_order, stop_loss_order).
        """
        # Determine the direction for profit and loss
        profit_direction = 1 if action == "BUY" else -1

        # Take Profit Order
        tp_price = round(open_execution_price * (1 + self.trade_management.take_profit_pct / 100 * profit_direction), 2)
        take_profit_order = Order()
        take_profit_order.orderId = self.ib_connector.get_next_request_id()
        take_profit_order.parentId = parent_order_id
        take_profit_order.action = "SELL" if action == "BUY" else "BUY"
        take_profit_order.orderType = "LMT"
        take_profit_order.lmtPrice = tp_price
        take_profit_order.totalQuantity = 1
        take_profit_order.transmit = False

        # Stop Loss Order
        sl_price = round(open_execution_price * (1 - self.trade_management.stop_loss_pct / 100 * profit_direction), 2)
        stop_loss_order = Order()
        stop_loss_order.orderId = self.ib_connector.get_next_request_id()
        stop_loss_order.parentId = parent_order_id
        stop_loss_order.action = "SELL" if action == "BUY" else "BUY"
        stop_loss_order.orderType = "STP"
        stop_loss_order.auxPrice = sl_price
        stop_loss_order.totalQuantity = 1
        stop_loss_order.transmit = True # Transmit the last order in the bracket

        logger.info(f"Created bracket orders for parent {parent_order_id}: TP at {tp_price}, SL at {sl_price}")
        
        return take_profit_order, stop_loss_order

    def place_trade(self, signal_type: SignalType, spot_price: float, strike_price: float, expiration_date: str):
        """
        Orchestrates the entire trade execution flow, including placing the opening
        order and subsequent bracket orders for take profit and stop loss.

        :param signal_type: The type of signal (e.g., SignalType.BUY for bullish).
        :param spot_price: Current market price of the underlying asset.
        :param strike_price: The specific strike price from GEX analysis.
        :param expiration_date: The contract expiration date (YYYYMMDD).
        """
        logger.info(f"Processing trade signal: {signal_type} at spot price {spot_price} with strike {strike_price}")

        # 1. Make Trade Decision
        option_type = self._make_trade_decision(signal_type, spot_price, strike_price)
        if not option_type:
            logger.info("Trade decision resulted in no action. Exiting.")
            return

        # 2. Fetch Option Chain to get available strikes
        logger.info(f"Fetching option chain for {self.contract_info.ticker} to determine ATM strike.")
        strike_list = self.ib_connector.fetch_option_chain(symbol=self.contract_info.ticker)
        
        # 3. Get ATM Strike
        atm_strike = self._get_atm_strike(spot_price, strike_list)
        if not atm_strike:
            logger.warning("Could not determine ATM strike from the fetched option chain. Aborting trade.")
            return

        # 4. Create Option Contract
        option_contract = self._create_option_contract(
            symbol=self.contract_info.ticker,
            atm_strike=atm_strike,
            option_type=option_type,
            expiration_date=expiration_date
        )

        # 5. Fetch Option Price
        option_price = self._fetch_option_price(option_contract)
        if not option_price:
            logger.error(f"Could not fetch market price for {option_contract.localSymbol}. Aborting.")
            return

        # 6. Place Opening Order and Handle Brackets
        self._place_full_bracket_trade(option_contract, option_price)
        logger.info("Successfully processed and placed complete bracket trade.")

    def _place_full_bracket_trade(self, contract: Contract, price: float):
        """
        Manages the entire lifecycle of a bracket order: places the parent,
        waits for the fill, and then places the children.
        """
        parent_order_id = self.ib_connector.get_next_request_id()

        # Create and place the parent order
        parent_order = Order()
        parent_order.orderId = parent_order_id
        parent_order.action = "BUY" # We are always buying calls or puts
        parent_order.orderType = self.order_defaults.entry_order_type
        parent_order.lmtPrice = price
        parent_order.totalQuantity = 1
        parent_order.transmit = False
        
        self.ib_connector.place_order(contract, parent_order, parent_order_id)
        logger.info(f"Placed parent order {parent_order_id} for {contract.localSymbol}. Waiting for fill...")

        # Wait for the parent order to be filled
        execution_price = None
        while True:
            status_update = self.ib_connector.get_order_status()
            if status_update and status_update[0] == parent_order_id:
                order_id, status, filled, remaining, avg_fill_price = status_update
                if status == 'Filled':
                    execution_price = avg_fill_price
                    logger.info(f"Parent order {order_id} filled at {execution_price}.")
                    break
                elif status in ['Cancelled', 'Inactive']:
                    logger.error(f"Parent order {order_id} was {status}. Aborting bracket orders.")
                    return
            time.sleep(1) # Avoid busy-waiting

        # Create and place the bracket orders
        take_profit_order, stop_loss_order = self._create_bracket_orders(
            parent_order_id=parent_order_id,
            open_execution_price=execution_price,
            action=parent_order.action
        )
        
        # Place Take Profit order
        self.ib_connector.place_order(contract, take_profit_order, take_profit_order.orderId)
        
        # Place Stop Loss order (and transmit the whole group)
        self.ib_connector.place_order(contract, stop_loss_order, stop_loss_order.orderId)
        
        # Store for trailing stop management
        self.active_positions[parent_order_id] = {
            "stop_loss_order_id": stop_loss_order.orderId,
            "contract": contract
        }
        logger.info(f"Placed bracket orders for parent {parent_order_id}. SL Order ID: {stop_loss_order.orderId}")

    def manage_open_positions(self):
        """
        Periodically called by the engine to manage trailing stops for open positions.
        """
        self.ib_connector.req_positions()
        open_positions = self.ib_connector.get_positions()

        if not open_positions:
            return

        for account, contract, position_size, avg_cost in open_positions:
            # Find the parent order ID associated with this contract
            parent_order_id = next(
                (pid for pid, data in self.active_positions.items() if data["contract"] == contract), 
                None
            )

            if not parent_order_id or position_size == 0:
                continue

            # --- Placeholder for fetching real-time data ---
            # In a real system, you'd fetch the current market price and P&L
            current_price = self._fetch_option_price(contract) # Re-using placeholder
            unrealized_pnl = (current_price - avg_cost) * position_size * 100 # Assuming multiplier 100
            
            # Check trailing stop conditions
            profit_pct = (current_price / avg_cost - 1) * 100
            activation_pct = self.trade_management.trailing_stop.activation_profit_pct
            
            if profit_pct > activation_pct:
                logger.info(f"Position for {contract.localSymbol} is profitable by {profit_pct:.2f}%. Checking trailing stop.")
                self._modify_stop_loss(parent_order_id, current_price)

    def _modify_stop_loss(self, parent_order_id: int, current_price: float):
        """
        Modifies the existing stop-loss order to a new trailing price.
        """
        position_data = self.active_positions.get(parent_order_id)
        if not position_data:
            return

        stop_loss_order_id = position_data["stop_loss_order_id"]
        contract = position_data["contract"]

        # Calculate new trailing stop price
        trail_pct = self.trade_management.trailing_stop.trail_pct
        new_stop_price = round(current_price * (1 - trail_pct / 100), 2)

        # Create a new order object with the SAME orderId
        modified_stop_order = Order()
        modified_stop_order.orderId = stop_loss_order_id
        modified_stop_order.action = "SELL" # Assuming we are long the option
        modified_stop_order.orderType = "STP"
        modified_stop_order.auxPrice = new_stop_price
        modified_stop_order.totalQuantity = 1
        modified_stop_order.transmit = True

        # Place the order to modify the existing one
        self.ib_connector.place_order(contract, modified_stop_order, stop_loss_order_id)
        logger.info(f"Modified Stop Loss for Parent Order {parent_order_id} (SL Order {stop_loss_order_id}) to new price {new_stop_price}.")

    def has_active_positions(self) -> bool:
        """
        Checks if there are any active positions being tracked.
        """
        return bool(self.active_positions)
