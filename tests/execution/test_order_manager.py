import pytest
from datetime import datetime
from unittest.mock import MagicMock, call

from execution.order_manager import OrderManager
from models.data_models import Signal, SignalType
from core.config_loader import AppConfig, TradeExecutionConfig, InstrumentConfig

@pytest.fixture
def mock_ib_connector():
    """Fixture for a mocked IBConnector."""
    connector = MagicMock()
    # Simulate the get_next_order_id behavior
    connector.get_next_order_id.side_effect = [100, 103, 106] # Returns a new ID each time
    return connector

@pytest.fixture
def mock_app_config(mocker):
    """Fixture for a mocked APP_CONFIG."""
    mock_config = AppConfig(
        connection=None, 
        account=None, 
        instrument=InstrumentConfig(ticker="SPY", exchange="SMART", currency="USD"),
        opening_range=None,
        breakout=None,
        gex=None,
        trade_execution=TradeExecutionConfig(
            take_profit_percentage=0.25, # Use different values than default
            stop_loss_percentage=0.15
        ),
        logging=None
    )
    mocker.patch('execution.order_manager.APP_CONFIG', mock_config)
    return mock_config

def test_place_bullish_trade(mock_ib_connector, mock_app_config):
    """
    Tests that a bullish trade is placed correctly with a bracket order.
    """
    # Arrange
    order_manager = OrderManager(ib_connector=mock_ib_connector)
    
    bullish_signal = Signal(timestamp=datetime.now(), symbol='SPY', signal_type=SignalType.BUY, strategy='test')
    spot_price = 450.0
    entry_price = 1.50 # This is still hardcoded in the OrderManager, which could be improved.
    
    # Act
    order_manager.place_trade(
        signal=bullish_signal,
        spot_price=spot_price,
        highest_gamma_strike=455.0, # Confirms bullish signal
        expiration='20240105'
    )

    # Assert
    assert mock_ib_connector.place_order.call_count == 3
    
    # Check the parent order
    parent_call = mock_ib_connector.place_order.call_args_list[0]
    parent_order = parent_call.args[2]
    assert parent_order.action == "BUY"
    assert parent_order.orderType == "LMT"
    assert parent_order.lmtPrice == entry_price
    assert parent_order.totalQuantity == 1
    assert not parent_order.transmit

    # Check the take profit order
    tp_call = mock_ib_connector.place_order.call_args_list[1]
    tp_order = tp_call.args[2]
    assert tp_order.action == "SELL"
    assert tp_order.lmtPrice == round(entry_price * 1.25, 2) # 1.50 * 1.25 = 1.875 -> 1.88
    
    # Check the stop loss order
    sl_call = mock_ib_connector.place_order.call_args_list[2]
    sl_order = sl_call.args[2]
    assert sl_order.action == "SELL"
    assert sl_order.orderType == "STP"
    assert sl_order.auxPrice == round(entry_price * (1 - 0.15), 2) # 1.50 * 0.85 = 1.275 -> 1.28
    assert sl_order.transmit
