# execution/order_manager.py

import logging
from ibapi.contract import Contract
from ibapi.order import Order

from ib_client.connector import IBConnector
from models.data_models import Signal, SignalType
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
        self.contract_info = APP_CONFIG.instrument.dict()
        self.trade_execution_config = APP_CONFIG.trade_execution

    def _get_atm_strike(self, spot_price: float) -> float:
        """
        Finds the At-The-Money (ATM) strike closest to the current spot price.
        """
        return round(spot_price / 5) * 5

    def _create_option_contract(self, strike: float, right: str, expiration: str) -> Contract:
        """
        Creates an option contract object.
        """
        contract = Contract()
        contract.symbol = self.contract_info['symbol']
        contract.secType = "OPT"
        contract.exchange = self.contract_info['exchange']
        contract.currency = self.contract_info['currency']
        contract.lastTradeDateOrContractMonth = expiration
        contract.strike = strike
        contract.right = right  # "C" for Call, "P" for Put
        contract.multiplier = "100"
        return contract

    def place_trade(self, signal: Signal, spot_price: float, highest_gamma_strike: float, expiration: str):
        """
        Places a trade based on the signal and market conditions.

        :param signal: The trading signal object.
        :param spot_price: The current spot price of the underlying.
        :param highest_gamma_strike: The strike with the highest gamma exposure.
        :param expiration: The expiration date for the option (YYYYMMDD).
        """
        trade_decision = self._make_trade_decision(signal, spot_price, highest_gamma_strike)
        if not trade_decision:
            return

        atm_strike = self._get_atm_strike(spot_price)
        option_contract = self._create_option_contract(atm_strike, trade_decision['right'], expiration)

        entry_price = 1.50  # Placeholder
        
        self._place_bracket_order(option_contract, entry_price, trade_decision['action'])

    def _make_trade_decision(self, signal: Signal, spot_price: float, highest_gamma_strike: float) -> dict:
        """
        Determines the trade to make based on the signal and GEX.
        """
        if signal.signal_type == SignalType.BUY and highest_gamma_strike > spot_price:
            logger.info("Bullish signal confirmed. Preparing Long Call order.")
            return {'action': 'BUY', 'right': 'C'}
        
        if signal.signal_type == SignalType.SELL and highest_gamma_strike < spot_price:
            logger.info("Bearish signal confirmed. Preparing Long Put order.")
            return {'action': 'BUY', 'right': 'P'}

        logger.info("Trade conditions not met. No order will be placed.")
        return {}

    def _place_bracket_order(self, contract: Contract, entry_price: float, action: str):
        """
        Creates and places a bracket order (entry, take profit, stop loss).
        """
        parent_order_id = self.ib_connector.get_next_order_id()

        take_profit_price = round(entry_price * (1 + self.trade_execution_config.take_profit_percentage), 2)
        stop_loss_price = round(entry_price * (1 - self.trade_execution_config.stop_loss_percentage), 2)
        
        parent = Order()
        parent.orderId = parent_order_id
        parent.action = action
        parent.orderType = "LMT"
        parent.lmtPrice = entry_price
        parent.totalQuantity = 1
        parent.transmit = False

        take_profit = Order()
        take_profit.orderId = parent_order_id + 1
        take_profit.action = "SELL" if action == "BUY" else "BUY"
        take_profit.orderType = "LMT"
        take_profit.lmtPrice = take_profit_price
        take_profit.totalQuantity = 1
        take_profit.parentId = parent_order_id
        take_profit.transmit = False

        stop_loss = Order()
        stop_loss.orderId = parent_order_id + 2
        stop_loss.action = "SELL" if action == "BUY" else "BUY"
        stop_loss.orderType = "STP"
        stop_loss.auxPrice = stop_loss_price
        stop_loss.totalQuantity = 1
        stop_loss.parentId = parent_order_id
        stop_loss.transmit = True

        logger.info(f"Placing bracket order for {contract.symbol} {contract.right} @ {contract.strike}:")
        logger.info(f"  Entry ({action}): {entry_price}")
        logger.info(f"  Take Profit: {take_profit_price}")
        logger.info(f"  Stop Loss: {stop_loss_price}")

        self.ib_connector.place_order(parent.orderId, contract, parent)
        self.ib_connector.place_order(take_profit.orderId, contract, take_profit)
        self.ib_connector.place_order(stop_loss.orderId, contract, stop_loss)


if __name__ == '__main__':
    from datetime import datetime

    class MockIBConnector:
        def __init__(self):
            self._next_order_id = 100
        
        def get_next_order_id(self):
            current_id = self._next_order_id
            self._next_order_id += 3 # Increment for bracket order
            return current_id

        def place_order(self, orderId, contract, order):
            print(f"Placing order {orderId} for {contract.symbol} {order.action} {order.totalQuantity} @ {order.lmtPrice or order.auxPrice}")

    ib_connector_mock = MockIBConnector()
    
    # In a real scenario, APP_CONFIG would be loaded. For this test, we mock it.
    class MockConfig:
        class Instrument:
            def dict(self):
                return {'symbol': 'SPY', 'exchange': 'SMART', 'currency': 'USD'}
        class TradeExecution:
            take_profit_percentage = 0.20
            stop_loss_percentage = 0.30
        
        instrument = Instrument()
        trade_execution = TradeExecution()

    APP_CONFIG = MockConfig()


    manager = OrderManager(ib_connector_mock)

    bullish_signal = Signal(timestamp=datetime.now(), symbol='SPY', signal_type=SignalType.BUY, strategy='test')
    bearish_signal = Signal(timestamp=datetime.now(), symbol='SPY', signal_type=SignalType.SELL, strategy='test')

    print("\n--- Bullish Scenario ---")
    manager.place_trade(
        signal=bullish_signal,
        spot_price=450.0,
        highest_gamma_strike=455.0,
        expiration='20240105'
    )
    
    print("\n--- Bearish Scenario ---")
    manager.place_trade(
        signal=bearish_signal,
        spot_price=450.0,
        highest_gamma_strike=445.0,
        expiration='20240105'
    )

    print("\n--- No Trade Scenario ---")
    manager.place_trade(
        signal=bullish_signal,
        spot_price=450.0,
        highest_gamma_strike=445.0, # Gamma does not confirm signal
        expiration='20240105'
    )