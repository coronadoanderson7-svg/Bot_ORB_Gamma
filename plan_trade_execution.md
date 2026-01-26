# Development Plan: Trade Execution Module

This document outlines the development plan for implementing the trade execution logic as specified in `Trade_execution_specification.md`.

## Phase 1: Configuration Setup

1.  **Update `config.yaml`:**
    *   Add the `trade_management` section with parameters for take profit, stop loss, and trailing stop as defined in the specification.
    ```yaml
    trade_management:
      take_profit_pct: 0.50
      stop_loss_pct: 0.20
      trailing_stop:
        activation_profit_pct: 0.10
        trail_pct: 0.10
    ```

2.  **Update `core/config_loader.py`:**
    *   Modify the configuration loading logic to parse and validate the new `trade_management` parameters, making them accessible throughout the application.

## Phase 2: Refactor `OrderManager` for New Trade Logic

The `execution/order_manager.py` will be the central component for this logic.

1.  **Create New Public Method `process_trade_signal`:**
    *   This method will be the new entry point called by the `Engine`.
    *   **Parameters:** `signal_type`, `spot_price`, `strike_price`, `expiration_date`.
    *   **Responsibility:** Orchestrate the entire trade execution flow from validation to order placement.

2.  **Implement Private Method `_make_trade_decision`:**
    *   **Parameters:** `signal_type`, `spot_price`, `strike_price`.
    *   **Logic:** Implement the 4-condition table from the specification to determine the option type (`'C'` for Call, `'P'` for Put).
    *   **Return:** The option type string or `None` if no trade should be executed.

3.  **Implement Private Method `_get_atm_strike`:**
    *   **Parameters:** `spot_price`, `strike_list`.
    *   **Logic:**
        *   This requires fetching available strikes first. A new method in `ib_client/client.py`, `fetch_option_chain`, will be needed to get strike data.
        *   Implement the logic to find the nearest strike to the `spot_price` from the fetched list.
    *   **Return:** The calculated ATM strike price.

4.  **Implement Private Method `_create_option_contract`:**
    *   **Parameters:** `symbol`, `atm_strike`, `option_type`, `expiration_date`.
    *   **Logic:** Use the inputs to create and configure an `ibapi.contract.Contract` object.
    *   **Return:** A fully populated `Contract` object.

5.  **Implement Private Method `_fetch_option_price`:**
    *   **Parameters:** `contract` object.
    *   **Logic:** This will call a new method in `ib_client/client.py` (`fetch_market_price`) that uses `reqMktData` to get the current price for the option.
    *   **Return:** The market price (e.g., ask price) for the option.

6.  **Implement Private Method `_place_opening_order`:**
    *   **Parameters:** `contract`, `price`.
    *   **Logic:**
        *   Create an `ibapi.order.Order` object (e.g., Limit order).
        *   Set `Transmit = False` to hold the order submission.
        *   Use the `ib_client` to get the next valid `orderId`.
        *   Store the opening order details (e.g., in a dictionary keyed by `orderId`).
        *   This method will prepare the opening order and the subsequent bracket orders.

## Phase 3: Implement Post-Trade Management

1.  **Implement Private Method `_create_bracket_orders`:**
    *   **Parameters:** `parent_order_id`, `open_execution_price`.
    *   **Logic:**
        *   Calculate the exact Take Profit and Stop Loss prices based on `open_execution_price` and percentages from the config.
        *   Create a `LMT` order for Take Profit and a `STP` order for Stop Loss.
        *   Set the `parentId` for both orders to `parent_order_id`.
        *   Set `Transmit = True` for the final order in the bracket to submit all three together.
    *   **Return:** A tuple containing the (take_profit_order, stop_loss_order).

2.  **Integrate Bracket Orders into the Flow:**
    *   After the opening order is placed, the `OrderManager` must wait for an execution confirmation from the `IBClient` wrapper.
    *   Once the fill is confirmed and the execution price is known, call `_create_bracket_orders` and place them.
    *   Store the `orderId` of the Stop Loss order in a persistent structure within `OrderManager` for later modification.

3.  **Implement `manage_open_positions` Method:**
    *   **Responsibility:** This method will be called periodically by the `Engine`'s main loop.
    *   **Logic:**
        *   Get open positions and their P&L from the `ib_client`.
        *   For each managed position, check if the trailing stop conditions are met (profit > activation % and < take profit %).
        *   If so, call a new private method `_modify_stop_loss`.

4.  **Implement Private Method `_modify_stop_loss`:**
    *   **Parameters:** `position`, `current_price`.
    *   **Logic:**
        *   Calculate the new trailing stop price based on the `trail_pct` from the config.
        *   Retrieve the existing Stop Loss `orderId` for the position.
        *   Create a new `STP` order object with the **same `orderId`** but the new stop price.
        *   Submit this order using `placeOrder` in the `ib_client` to modify the existing server-side order.

## Phase 4: `IBClient` Modifications (`ib_client/client.py`)

1.  **`fetch_option_chain`:** Implement to get contract details, including available strikes.
2.  **`fetch_market_price`:** Implement to get a single price quote for a contract.
3.  **Callback Handling:** Ensure callbacks like `orderStatus` and `execDetails` are robustly handled in `ib_client/wrapper.py` and that the data is passed back to `OrderManager` to confirm fills and execution prices.

## Phase 5: Testing (`tests/execution/test_order_manager.py`)

1.  **Mock `IBClient`:** Create a comprehensive mock of the `IBClient` to simulate API responses for all new methods.
2.  **Test `_make_trade_decision`:** Write tests for all 4 conditions in the logic table.
3.  **Test `_get_atm_strike`:** Test the rounding and selection logic.
4.  **Test Bracket Order Creation:** Verify that `_create_bracket_orders` calculates prices correctly and structures the orders with the correct `parentId`.
5.  **Test Trailing Stop Logic:**
    *   Simulate a position's P&L changing over time.
    *   Verify that `manage_open_positions` correctly identifies when to trail the stop.
    *   Verify that `_modify_stop_loss` is called with the correct parameters and that it attempts to place an order with the correct (old) `orderId` and new price.
