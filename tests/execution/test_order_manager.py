import pytest
from unittest.mock import MagicMock, call
from execution.order_manager import OrderManager
from models.data_models import SignalType
from core.config_loader import (
    AppConfig, InstrumentConfig, TradeManagementConfig, TrailingStopConfig, 
    TradeExecutionConfig, OrderDefaultsConfig, ConnectionConfig, AccountConfig,
    OpeningRangeConfig, BreakoutConfig, GEXConfig, LoggingConfig,
    ProvidersConfig, GexbotConfig, MassiveDataConfig
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
    # Define dummy provider configs to satisfy the model validation
    mock_providers = ProvidersConfig(
        gexbot=GexbotConfig(api_key="dummy_gexbot_key", base_url="http://dummy.gexbot.com"),
        massive_data=MassiveDataConfig(api_key="dummy_massive_key", base_url="http://dummy.massive.com")
    )

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
        gex=GEXConfig(
            days_to_expiration=0, 
            strikes_quantity=20, 
            option_multiplier=100,
            provider_type=1,  # Provide a default provider type
            providers=mock_providers # Provide the nested provider config
        ),
        trade_management=TradeManagementConfig(
            take_profit_pct=50.0,
            stop_loss_pct=20.0,
            trailing_stop=TrailingStopConfig(
                activation_profit_pct=10.0,
                trail_pct=10.0
            )
        ),
        trade_execution=TradeExecutionConfig(
            total_quantity=2, # Added for completeness
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

# -----------------------------------------------------------------------------
# Test Cases for Broker Price Conformance (The Fix)
# -----------------------------------------------------------------------------

@pytest.mark.parametrize("price, tick_size, expected", [
    (19.67, 0.05, 19.65),    # Round down to nearest 0.05
    (19.68, 0.05, 19.70),    # Round up to nearest 0.05
    (22.11, 0.10, 22.10),    # Round down to nearest 0.10
    (22.18, 0.10, 22.20),    # Round up to nearest 0.10
    (15.50, 0.05, 15.50),    # Already on tick
    (10.03, 0, 10.03),        # Invalid tick size, defaults to 2 decimal rounding
    (10.03, None, 10.03),     # Invalid tick size, defaults to 2 decimal rounding
])
def test_round_to_tick_size(order_manager, price, tick_size, expected):
    """Tests the price rounding logic with various tick sizes."""
    assert order_manager._round_to_tick_size(price, tick_size) == expected

def test_create_bracket_orders_new(order_manager, mock_config):
    """
    Tests the refactored creation of take profit and stop loss orders, 
    ensuring prices are correctly sanitized.
    """
    # Arrange
    parent_id = 100
    exec_price = 2.33  # A price not on a standard tick
    quantity = 2
    min_tick = 0.05    # A standard tick size for options
    
    # --- Test Case 1: Standard TP/SL calculation ---
    
    # Act
    result = order_manager._create_bracket_orders(parent_id, exec_price, quantity, "BUY", min_tick)
    assert result is not None
    tp_order, sl_order = result

    # Assert
    # TP: 2.33 * (1 + 50%) = 3.495 -> rounded to 3.50
    assert tp_order.parentId == parent_id
    assert tp_order.action == "SELL"
    assert tp_order.orderType == "LMT"
    assert tp_order.lmtPrice == 3.50
    assert tp_order.totalQuantity == quantity
    assert tp_order.tif == "GTC"
    assert not tp_order.transmit

    # SL: 2.33 * (1 - 20%) = 1.864 -> rounded to 1.85
    assert sl_order.parentId == parent_id
    assert sl_order.action == "SELL"
    assert sl_order.orderType == "STP"
    assert sl_order.auxPrice == 1.85
    assert sl_order.totalQuantity == quantity
    assert sl_order.tif == "GTC"
    assert sl_order.transmit

    # --- Test Case 2: SL price is at entry, should be adjusted down ---
    mock_config.trade_management.stop_loss_pct = 1.0 # Set SL to 1%
    
    # Act
    result_adj = order_manager._create_bracket_orders(parent_id, 2.33, quantity, "BUY", min_tick)
    assert result_adj is not None
    _, sl_order_adj = result_adj

    # Assert
    # SL: 2.33 * (1 - 1%) = 2.3067 -> rounded to 2.30. This is below entry, so no adjustment needed.
    # Let's try a case where it IS adjusted.
    # SL: 2.33 * (1 - 0.1%) = 2.32767 -> rounded to 2.35. This is ABOVE entry.
    mock_config.trade_management.stop_loss_pct = 0.1
    result_adj_2 = order_manager._create_bracket_orders(parent_id, 2.33, quantity, "BUY", min_tick)
    assert result_adj_2 is not None
    _, sl_order_adj_2 = result_adj_2
    # Raw SL is 2.32767, which rounds to 2.35. Since 2.35 > 2.33, it's adjusted down by one tick.
    assert sl_order_adj_2.auxPrice == 2.30 # 2.35 - 0.05

    # --- Test Case 3: Unsupported action ---
    assert order_manager._create_bracket_orders(parent_id, exec_price, quantity, "SELL", min_tick) is None


# -----------------------------------------------------------------------------
# Original Test Cases
# -----------------------------------------------------------------------------


def test_place_trade_full_flow(order_manager, mock_ib_connector, mock_config):
    """
    Tests the entire place_trade flow, mocking dependencies and verifying
    both the initial parent order placement and the subsequent bracket order
    placement after a fill.
    """
    # --- Arrange: Phase 1 (Parent Order) ---
    parent_order_id = 100
    mock_ib_connector.place_order.return_value = parent_order_id
    mock_ib_connector.fetch_market_price.return_value = {'ask': 1.50}
    mock_ib_connector.resolve_contract_details.return_value.minTick = 0.01

    # --- Act: Phase 1 (Place Parent Order) ---
    order_manager.place_trade(
        signal_type=SignalType.BUY,
        spot_price=451,      # -> ATM should be 450
        strike_price=455,    # -> Bullish signal, GEX above -> Call
        expiration_date="20251219",
        strike_list=[440, 445, 450, 455, 460]
    )

    # --- Assert: Phase 1 (Parent Order Correctness) ---
    # 1. Market price was fetched for the correct ATM contract
    fetch_price_call = mock_ib_connector.fetch_market_price.call_args
    contract_arg = fetch_price_call.args[0]
    assert isinstance(contract_arg, Contract)
    assert contract_arg.strike == 450
    assert contract_arg.right == 'C'

    # 2. Parent order was placed once with correct details
    mock_ib_connector.place_order.assert_called_once()
    parent_call = mock_ib_connector.place_order.call_args_list[0]
    placed_parent_contract, placed_parent_order = parent_call.args
    assert placed_parent_contract == contract_arg  # Ensure it's the same contract
    assert placed_parent_order.lmtPrice == 1.50 # from mocked market price
    assert placed_parent_order.totalQuantity == mock_config.trade_execution.total_quantity
    assert placed_parent_order.tif == "DAY"

    # --- Arrange: Phase 2 (Bracket Orders) ---
    # Mock the order status queue to signal a fill for the parent order
    mock_queue = MagicMock()
    mock_queue.empty.side_effect = [False, True]  # Process one item, then stop
    mock_queue.get_nowait.return_value = {
        'orderId': parent_order_id,
        'status': 'Filled',
        'avgFillPrice': 1.48,
        'filled': mock_config.trade_execution.total_quantity,
        'remaining': 0
    }
    mock_ib_connector.get_order_status_queue.return_value = mock_queue
    # Set up request IDs for the upcoming bracket orders
    mock_ib_connector.get_next_request_id.side_effect = [101, 102]

    # --- Act: Phase 2 (Process Fills and Place Brackets) ---
    order_manager.check_fills_and_place_brackets()

    # --- Assert: Phase 2 (Bracket Orders Correctness) ---
    # 3. place_order was called again for TP and SL orders
    assert mock_ib_connector.place_order.call_count == 3

    # TP order (ID 101), based on fill price 1.48
    # TP = 1.48 * (1 + 50%) = 2.22
    tp_call = mock_ib_connector.place_order.call_args_list[1]
    tp_order = tp_call.args[1]
    assert tp_order.orderId == 101
    assert tp_order.parentId == parent_order_id
    assert tp_order.lmtPrice == 2.22
    assert tp_order.tif == "GTC"

    # SL order (ID 102), based on fill price 1.48
    # SL = 1.48 * (1 - 20%) = 1.184 -> rounded to 1.18
    sl_call = mock_ib_connector.place_order.call_args_list[2]
    sl_order = sl_call.args[1]
    assert sl_order.orderId == 102
    assert sl_order.parentId == parent_order_id
    assert sl_order.auxPrice == 1.18
    assert sl_order.tif == "GTC"

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
        "contract": contract,
        "min_tick": 0.01
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
    assert modified_order.tif == "GTC"

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