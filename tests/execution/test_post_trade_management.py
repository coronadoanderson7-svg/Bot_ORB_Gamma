import pytest
from unittest.mock import MagicMock, call, patch
from ibapi.contract import Contract
from ibapi.order import Order

from execution.order_manager import OrderManager
from models.data_models import SignalType
from core.config_loader import APP_CONFIG


@pytest.fixture
def mock_ib_connector():
    """Fixture for a mocked IBConnector."""
    connector = MagicMock()
    # Simulate the get_next_request_id behavior
    connector.get_next_request_id.side_effect = [100, 101, 102, 103, 104, 105] 
    return connector

@pytest.fixture
def order_manager(mock_ib_connector):
    """Fixture for an OrderManager instance with a mocked connector."""
    with patch('execution.order_manager.APP_CONFIG', new_callable=MagicMock) as mock_config:
        mock_config.instrument.ticker = "SPY"
        mock_config.instrument.exchange = "SMART"
        mock_config.instrument.currency = "USD"
        mock_config.trade_execution.order_defaults.entry_order_type = "LMT"
        mock_config.trade_management.take_profit_pct = 50.0
        mock_config.trade_management.stop_loss_pct = 20.0
        mock_config.trade_management.trailing_stop.activation_pct = 10.0
        mock_config.trade_management.trailing_stop.trail_pct = 10.0

        manager = OrderManager(ib_connector=mock_ib_connector)
        # Mock the internal price fetcher for predictability
        with patch.object(manager, '_fetch_option_price', return_value=1.50) as _:
            yield manager

def test_place_full_bracket_trade(order_manager: OrderManager, mock_ib_connector: MagicMock):
    """
    Tests the entire bracket order placement flow, from parent order to children,
    including waiting for the fill.
    """
    # Arrange
    parent_order_id = 100
    # Simulate the fill confirmation from the queue
    mock_ib_connector.get_order_status.return_value = (parent_order_id, 'Filled', 1.0, 0, 1.45)

    # Act
    order_manager.place_trade(
        signal_type=SignalType.BUY,
        spot_price=450.0,
        strike_price=455.0, # Bullish condition
        expiration_date="20250101"
    )

    # Assert
    assert mock_ib_connector.place_order.call_count == 3
    
    # 1. Parent Order
    parent_call = mock_ib_connector.place_order.call_args_list[0]
    parent_contract, parent_order, p_order_id = parent_call.args
    assert p_order_id == parent_order_id
    assert parent_order.action == "BUY"
    assert parent_order.orderType == "LMT"
    assert parent_order.lmtPrice == 1.50 # From the mocked _fetch_option_price
    assert not parent_order.transmit

    # 2. Take Profit Order
    tp_call = mock_ib_connector.place_order.call_args_list[1]
    _, tp_order, tp_order_id = tp_call.args
    assert tp_order_id == 101
    assert tp_order.parentId == parent_order_id
    assert tp_order.action == "SELL"
    assert tp_order.orderType == "LMT"
    assert tp_order.lmtPrice == round(1.45 * (1 + 0.50), 2) # Based on actual fill price
    assert not tp_order.transmit
    
    # 3. Stop Loss Order
    sl_call = mock_ib_connector.place_order.call_args_list[2]
    _, sl_order, sl_order_id = sl_call.args
    assert sl_order_id == 102
    assert sl_order.parentId == parent_order_id
    assert sl_order.action == "SELL"
    assert sl_order.orderType == "STP"
    assert sl_order.auxPrice == round(1.45 * (1 - 0.20), 2) # Based on actual fill price
    assert sl_order.transmit

    # Verify the position is being tracked
    assert parent_order_id in order_manager.active_positions
    assert order_manager.active_positions[parent_order_id]["stop_loss_order_id"] == sl_order_id

def test_manage_open_positions_triggers_modification(order_manager: OrderManager, mock_ib_connector: MagicMock):
    """
    Tests that manage_open_positions correctly identifies a profitable position
    and calls the modification logic.
    """
    # Arrange
    parent_order_id = 100
    sl_order_id = 102
    
    # Setup an active position to be managed
    contract = Contract()
    contract.symbol = "SPY"
    contract.secType = "OPT"
    contract.localSymbol = "SPY 250101C00455000"

    order_manager.active_positions[parent_order_id] = {
        "stop_loss_order_id": sl_order_id,
        "contract": contract
    }
    
    # Simulate the response from reqPositions()
    # (account, contract, position_size, avg_cost)
    mock_ib_connector.get_positions.return_value = [
        ("DU12345", contract, 1.0, 1.45)
    ]
    
    # Mock the price fetcher to return a profitable price
    with patch.object(order_manager, '_fetch_option_price', return_value=1.80) as mock_fetch:
        # Act
        order_manager.manage_open_positions()

    # Assert
    # Check that positions were requested
    mock_ib_connector.req_positions.assert_called_once()
    
    # Check that a new stop loss order was placed (i.e., modification)
    # It should be the 1st call because place_trade is not called
    assert mock_ib_connector.place_order.call_count == 1
    
    mod_call = mock_ib_connector.place_order.call_args_list[0]
    _, mod_order, mod_order_id = mod_call.args
    
    assert mod_order_id == sl_order_id # Must use the same ID
    assert mod_order.orderType == "STP"
    # New stop price should be 10% below the new current_price of 1.80
    assert mod_order.auxPrice == round(1.80 * (1 - 0.10), 2)

def test_modify_stop_loss_logic(order_manager: OrderManager, mock_ib_connector: MagicMock):
    """
    Tests the _modify_stop_loss private method directly to ensure it
    constructs and places the correct modification order.
    """
    # Arrange
    parent_order_id = 100
    sl_order_id = 102
    current_price = 2.0
    
    contract = Contract()
    contract.symbol = "SPY"
    
    order_manager.active_positions[parent_order_id] = {
        "stop_loss_order_id": sl_order_id,
        "contract": contract
    }
    
    # Act
    order_manager._modify_stop_loss(parent_order_id, current_price)
    
    # Assert
    mock_ib_connector.place_order.assert_called_once()
    
    mod_call = mock_ib_connector.place_order.call_args_list[0]
    mod_contract, mod_order, mod_order_id = mod_call.args
    
    assert mod_contract == contract
    assert mod_order_id == sl_order_id # Modifies existing order
    assert mod_order.orderType == "STP"
    assert mod_order.action == "SELL"
    assert mod_order.totalQuantity == 1
    assert mod_order.transmit
    
    # New stop is 10% below current price: 2.0 * (1 - 0.10) = 1.80
    assert mod_order.auxPrice == 1.80

