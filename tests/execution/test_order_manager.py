import pytest
from unittest.mock import MagicMock, call
from execution.order_manager import OrderManager
from models.data_models import SignalType
from core.config_loader import (
    AppConfig, InstrumentConfig, TradeManagementConfig, TrailingStopConfig, 
    TradeExecutionConfig, OrderDefaultsConfig, ConnectionConfig, AccountConfig,
    OpeningRangeConfig, BreakoutConfig, GEXConfig, LoggingConfig
)
from ibapi.contract import Contract
from ibapi.order import Order

@pytest.fixture
def mock_ib_connector():
    """A pytest fixture that provides a mocked IBConnector instance."""
    connector = MagicMock()
    connector.get_next_request_id.side_effect = range(100, 120) 
    return connector

@pytest.fixture
def mock_config(mocker):
    """A pytest fixture that mocks the application's configuration."""
    mock_cfg = AppConfig(
        connection=ConnectionConfig(host="127.0.0.1", port=4002, client_id=1),
        account=AccountConfig(type="paper", code="DU12345"),
        instrument=InstrumentConfig(ticker="SPY", exchange="SMART", currency="USD", exchange_timezone="America/New_York"),
        opening_range=OpeningRangeConfig(
            market_open_time="09:30:00",
            duration_minutes=15,
            bar_size="1 min",
            wait_buffer_seconds=5,
            historical_data_timeout_seconds=30
        ),
        breakout=BreakoutConfig(bar_size_seconds=5),
        gex=GEXConfig(days_to_expiration=0, strikes_quantity=20, option_multiplier=100),
        trade_management=TradeManagementConfig(
            take_profit_pct=50.0,
            stop_loss_pct=20.0,
            trailing_stop=TrailingStopConfig(
                activation_profit_pct=10.0,
                trail_pct=10.0
            )
        ),
        trade_execution=TradeExecutionConfig(
            order_defaults=OrderDefaultsConfig(
                entry_order_type="LMT",
                tp_order_type="LMT",
                sl_order_type="STP"
            )
        ),
        logging=LoggingConfig(log_level="INFO", log_file="test_bot.log")
    )
    mocker.patch('execution.order_manager.APP_CONFIG', mock_cfg)
    return mock_cfg

@pytest.fixture
def order_manager(mock_ib_connector, mock_config):
    """A pytest fixture that provides an OrderManager instance with mocked dependencies."""
    return OrderManager(ib_connector=mock_ib_connector)

# -----------------------------------------------------------------------------
# Test Cases for Issue #4: Incorrect Trade Decision Logic
# -----------------------------------------------------------------------------

@pytest.mark.parametrize("signal_type, spot_price, strike_price, expected_action", [
    (SignalType.BUY, 450, 455, 'C'),  # Bullish signal, GEX above spot -> Call
    (SignalType.BUY, 450, 445, 'P'),  # Bullish signal, GEX below spot -> Put
    (SignalType.SELL, 450, 455, 'C'), # Bearish signal, GEX above spot -> Call
    (SignalType.SELL, 450, 445, 'P'), # Bearish signal, GEX below spot -> Put
])
def test_make_trade_decision(order_manager, signal_type, spot_price, strike_price, expected_action):
    """Tests the _make_trade_decision logic for all four specified conditions."""
    # Act
    action = order_manager._make_trade_decision(signal_type, spot_price, strike_price)
    # Assert
    assert action == expected_action

# -----------------------------------------------------------------------------
# Test Cases for Issue #3: ATM Strike Calculation
# -----------------------------------------------------------------------------

def test_get_atm_strike_finds_closest(order_manager):
    """Tests that _get_atm_strike finds the closest strike in a list."""
    # Arrange
    strike_list = [440, 445, 450, 455, 460]
    # Act & Assert
    assert order_manager._get_atm_strike(451.5, strike_list) == 450
    assert order_manager._get_atm_strike(453.5, strike_list) == 455
    assert order_manager._get_atm_strike(438, strike_list) == 440

def test_get_atm_strike_empty_list(order_manager):
    """Tests that _get_atm_strike returns None for an empty list."""
    # Act & Assert
    assert order_manager._get_atm_strike(450, []) is None

# -----------------------------------------------------------------------------
# Test Cases for Bracket and Trailing Stop Logic (related to Issue #2)
# -----------------------------------------------------------------------------

def test_create_bracket_orders(order_manager):
    """
    Tests the creation of take profit and stop loss orders with correct prices.
    """
    # Arrange
    parent_id = 100
    exec_price = 2.00
    # Act
    tp_order, sl_order = order_manager._create_bracket_orders(parent_id, exec_price, "BUY")
    
    # Assert
    # Take Profit: 2.00 * (1 + 50%) = 3.00
    assert tp_order.orderId == 100
    assert tp_order.parentId == parent_id
    assert tp_order.action == "SELL"
    assert tp_order.orderType == "LMT"
    assert tp_order.lmtPrice == 3.00
    assert not tp_order.transmit

    # Stop Loss: 2.00 * (1 - 20%) = 1.60
    assert sl_order.orderId == 101
    assert sl_order.parentId == parent_id
    assert sl_order.action == "SELL"
    assert sl_order.orderType == "STP"
    assert sl_order.auxPrice == 1.60
    assert sl_order.transmit

def test_place_trade_full_flow(order_manager, mock_ib_connector):
    """
    Tests the entire place_trade flow, mocking dependencies.
    This also covers the fix for ATM Strike Calculation (Issue #3).
    """
    # Arrange
    mock_ib_connector.fetch_option_chain.return_value = [440, 445, 450, 455, 460]
    mock_ib_connector.fetch_market_price.return_value = {'ask': 1.50}
    # Simulate a 'Filled' status update from the queue
    mock_ib_connector.get_order_status.return_value = (100, 'Filled', 1, 0, 1.48) 

    # Act
    order_manager.place_trade(
        signal_type=SignalType.BUY,
        spot_price=451,      # -> ATM should be 450
        strike_price=455,    # -> Bullish signal, GEX above -> Call
        expiration_date="20251219"
    )

    # Assert
    # 1. Option chain was fetched
    mock_ib_connector.fetch_option_chain.assert_called_once_with(symbol="SPY")
    
    # 2. Market price was fetched for the correct ATM contract
    fetch_price_call = mock_ib_connector.fetch_market_price.call_args
    contract_arg = fetch_price_call.args[0]
    assert isinstance(contract_arg, Contract)
    assert contract_arg.strike == 450
    assert contract_arg.right == 'C'

    # 3. Correct bracket orders were placed after fill confirmation
    assert mock_ib_connector.place_order.call_count == 3
    
    # Parent order (ID 100)
    parent_call = mock_ib_connector.place_order.call_args_list[0]
    assert parent_call.args[1].orderId == 100
    assert parent_call.args[1].lmtPrice == 1.50 # from mocked market price

    # TP order (ID 101), based on fill price 1.48
    # 1.48 * 1.50 = 2.22
    tp_call = mock_ib_connector.place_order.call_args_list[1]
    assert tp_call.args[1].orderId == 101
    assert tp_call.args[1].lmtPrice == 2.22

    # SL order (ID 102), based on fill price 1.48
    # 1.48 * 0.80 = 1.184 -> 1.18
    sl_call = mock_ib_connector.place_order.call_args_list[2]
    assert sl_call.args[1].orderId == 102
    assert sl_call.args[1].auxPrice == 1.18

def test_manage_open_positions_triggers_trailing_stop(order_manager, mock_ib_connector):
    """
    Tests that manage_open_positions correctly identifies a profitable position
    and modifies the stop loss order. This covers the main part of Issue #2.
    """
    # Arrange
    # Setup an active position as if it was placed earlier
    parent_order_id = 99
    sl_order_id = 105
    contract = Contract()
    contract.symbol = "SPY"
    contract.localSymbol = "SPY 251219C00450000"
    
    order_manager.active_positions[parent_order_id] = {
        "stop_loss_order_id": sl_order_id,
        "contract": contract
    }

    # Simulate IB telling us we have an open position
    mock_ib_connector.get_positions.return_value = [
        ("U123", contract, 1, 2.00) # account, contract, size, avg_cost
    ]
    
    # Simulate market price having risen past the activation threshold (10%)
    # Current profit: (2.30 / 2.00) - 1 = 15%
    mock_ib_connector.fetch_market_price.return_value = {'last': 2.30}

    # Act
    order_manager.manage_open_positions()

    # Assert
    # It should have placed an order to MODIFY the existing stop loss
    assert mock_ib_connector.place_order.call_count == 1
    
    modify_call = mock_ib_connector.place_order.call_args
    modified_contract = modify_call.args[0]
    modified_order = modify_call.args[1]
    
    assert modified_contract == contract
    assert modified_order.orderId == sl_order_id # Crucially, it uses the OLD orderId
    assert modified_order.orderType == "STP"

    # New stop price: 2.30 * (1 - 10%) = 2.07
    assert modified_order.auxPrice == 2.07
    assert modified_order.transmit

def test_has_active_positions(order_manager):
    """Tests the has_active_positions helper method."""
    assert not order_manager.has_active_positions()
    order_manager.active_positions[100] = {}
    assert order_manager.has_active_positions()
    del order_manager.active_positions[100]
    assert not order_manager.has_active_positions()