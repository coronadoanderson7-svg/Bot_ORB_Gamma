Project Summary
The objective of this project is to develop an algorithmic trading engine designed to operate in the 0DTE (Zero Days to Expiration) options market. The system follows a structured, multi-stage workflow to identify and execute high-probability trades.
Core Processes: 

Opening Range Identification: Define the initial price range during the opening period.
Breakout Detection: Monitor and detect valid breakouts from the established opening range.
Gamma Exposure (GEX) Analysis: Calculate and incorporate GEX metrics to enhance trade selection.
Trade Execution: Systematically open and close positions based on signal confirmation.


**Stage 1: Opening Range Identification**

The goal is to define the initial price range during the first 30 minutes of the market session.

Step 1: IB API Communication Flow (High-Level)

Step,API Client Action (You Send),TWS/IB Gateway Action (You Receive)
Setup,"1. Connect to TWS/IB Gateway (e.g., eClient.connect(...)).","2. Connection established (e.g., eWrapper.connectionTime(...) is called)."
Contract,"3. Define the contract for your ticker (e.g., Contract object: symbol, secType, exchange, currency).","No immediate response, this is local."
Request Data,"4. Send the historical data request (e.g., eClient.reqHistoricalData(...)).","5. Data received in bars (e.g., eWrapper.historicalData(...) is called repeatedly for each bar)."
Data Received,,"6. End of data stream (e.g., eWrapper.historicalDataEnd(...) is called to signal completion)."
Cleanup,"7. Disconnect (e.g., eClient.disconnect()).",Connection is closed.

Step 2: Request Parameters (First 30 Minutes)

contract: The ticker of interest (e.g., AAPL).
endDateTime: Set to the current date and 30 minutes after market open (e.g., 09:30:00 EST + 30 mins).
durationStr: Set to '30 min' to define the historical data window.
barSizeSetting: Set to '1 min' resolution to accurately capture high/low.
whatToShow: Use 'TRADES' for open, high, low, close, and volume.
useRTH: Set to 1 (True) to ignore pre-market data

Step 3: Calculating Levels

Store Bar Data: Collect High and Low prices for every 1-minute bar received.
Filter/Validate: Ensure bars strictly fall within the market open window (no pre-market).
Find Range: Once historicalDataEnd is received:
HIGH_LEVEL: The maximum value of all collected High prices.
LOW_LEVEL: The minimum value of all collected Low prices.


**Stage 2: Breakout Detection**

Monitor real-time data to detect clean breakouts from the established range.

Step 1: Real-Time Data Flow
Setup: Ensure the TWS/Gateway connection is active.
Request Data: Send a request using eClient.reqRealTimeBars(...). Receive data via eWrapper.realtimeBar(...) every time a bar closes.
Processing: Client-side code aggregates 5-second bars into 5-minute candles and applies logic.
Cleanup: Cancel the subscription using eClient.cancelRealTimeBars(...) when finished.

Step 2: Breakout Calculation Conditions

Let the 5-minute candle consist of: $C_{High}$, $C_{Low}$, $C_{Open}$, and $C_{Close}$.

High Breakout (Bullish Signal):
Direction: Must be a bullish candle ($C_{Close} > C_{Open}$)
Clean Break: The entire body must be above the level ($C_{Low} > HIGH\_LEVEL$)

Low Breakout (Bearish Signal):
Direction: Must be a bearish candle ($C_{Close} < C_{Open}$)
Clean Break: The entire body must be below the level ($C_{High} < LOW\_LEVEL$)

Signal Result:

If High Breakout is true: BULLISH.
If Low Breakout is true: BEARISH.
Otherwise: NO SIGNAL.


**Stage 3: Gamma Exposure (GEX) Analysis**

Objective: create a third stage where we will get the gamma exposure in three different ways, to be used in the four stage: 

    * We will start creating a parameter in the config.yaml where we are going to be able to select the type of process that calculate the GEX
        The parameter will have: 

            1. Name: GEX Process type
            2. it needs to be initialized as 0, but can be 0,1 or 2 

    * If GEX Process type = 0 the program will use the Option 1 Use a Third-Party GEX Service (gexbot)
    * If GEX Process type = 1 the program will use the Option 2 Build a Parallelized "GEX Microservice"
    * If GEX Process type = 2 the program will use the Option 3 Use a Dedicated Data Feed

    # Option 1 Use a Third-Party GEX Service (gexbot) - Process Specification: GEX Calculation via Third-Party Service (gexbot)

        This document outlines the technical specification for **Option 1: Use a Third-Party GEX Service (gexbot)**.
        The process leverages the `gexbot.com` REST API to acquire gamma distribution data.

    **Objective:** To identify the single options strike price with the highest absolute concentration of gamma exposure for a given underlying and expiration. 
        This strike level, referred to as `MAX_GAMMA_STRIKE`, will be used as a key input for the trade validation logic in Stage 4.

        ---

        ### Step 1: Connection & Authentication

        **Objective:** Establish a secure, authenticated session with the `gexbot.com` API.

        1.  **Action:** The system will initiate a secure HTTPS connection to the API's base endpoint.
        2.  **Authentication:** Every request must include the API Key as a query parameter in the URL.
            *   **URL Format:** `https://api.gexbot.com/v1/...?api_key=<YOUR_API_KEY>`
        3.  **Parameters Required (from `config.yaml`):**
            *   `gexbot_api_key`: The secret API key for the `gexbot.com` service.
            *   `gexbot_base_url`: The root URL for the API (`https://api.gexbot.com/`).
        4.  **Error Handling:**
            *   If a `401 Unauthorized` response is received, the connection has failed due to an invalid API key. The system should log a critical error and halt the GEX calculation process.
            *   Connection timeouts or other network-level errors should trigger a retry mechanism before failing.

        ---

        ### Step 2: Data Retrieval (Gamma Fetch)

        **Objective:** Fetch the raw gamma distribution data for a specific ticker and expiration date in a single API call.

        1.  **Action:** The system will send a single `GET` request to the gamma distribution endpoint.
        2.  **Endpoint:** `/v1/gex/distribution`
        3.  **Request Parameters:**
            *   `api_key` (string, required): The authentication key.
            *   `ticker` (string, required): The underlying symbol (e.g., "SPX").
            *   `exp` (string, required): The target expiration date in `YYYY-MM-DD` format. The system will construct this date based on the `days_to_expiration` setting in `config.yaml`.
        4.  **Expected Response (JSON):** The API will return a JSON object containing a `data` array. Each element in the array represents a single strike and its associated gamma values.

            ```json
            {
            "success": true,
            "data": [
                {
                "strike": 5000,
                "long_gamma": 1234567.89,
                "short_gamma": -987654.32,
                "total_gamma": 246913.57,
                "vanna": ...,
                "charm": ...
                },
                {
                "strike": 5010,
                "long_gamma": 1100000.00,
                "short_gamma": -1050000.00,
                "total_gamma": 50000.00,
                ...
                },
                // ... more strikes
            ]
            }
            ```

        ---

        ### Step 3: Aggregation (Absolute Value Summation)

        **Objective:** To determine the total magnitude of gamma risk at each strike, irrespective of whether it comes from long or short positions.

        1.  **Logic:** For every unique strike `K` returned by the API, the system calculates the **Total Gamma Exposure** by summing the absolute values of the long and short gamma.
        The `total_gamma` field from the API response is ignored, as it represents a net sum, not the sum of magnitudes.

            `Total_GEX_K = ABS(Short_Gamma_K) + ABS(Long_Gamma_K)`

        2.  **Process:** The system will iterate through the `data` array from the API response. 
        For each strike, it will perform the absolute summation and store the result in a dictionary where the key is the strike price and the value is its calculated `Total_GEX`.

            **Example Resulting Structure:**
            ```
            {
            5000: 2222222.21,  // abs(-987654.32) + abs(1234567.89)
            5010: 2150000.00,  // abs(-1050000.00) + abs(1100000.00)
            ...
            }
            ```

        ---

        ### Step 4: Max GEX Identification

        **Objective:** Isolate the single strike price with the highest concentration of total gamma to be used in the trading logic.

        1.  **Operation:** The system will perform a "max" search on the aggregated GEX results from Step 3. It will identify the key (strike) that corresponds to the largest value (Total GEX).
        2.  **Variable Assignment:** The strike price with the highest `Total_GEX` value is stored in a variable for use in Stage 4.
            *   **Variable Name:** `MAX_GAMMA_STRIKE`

        **Final Output:** The `MAX_GAMMA_STRIKE` variable, holding a single float value (e.g., `5000.0`), is returned by the process. 
        This value is now ready to be consumed by the `Trade Execution` stage.


    Option 2: Build a Parallelized "GEX Microservice" - GEX Process type = 1 

     # Specification: Interactive Brokers GEX Provider (`IBProvider`)

        ## 1. Introduction & Purpose

        This document outlines the specification for creating a new Gamma Exposure (GEX) data provider, the `IBProvider`. This provider will calculate GEX by fetching real-time options and market data directly from Interactive Brokers (IB).

        The primary goals of this provider are:
        - To offer a self-sufficient, cost-effective method for calculating GEX without relying on third-party paid APIs.
        - To increase the application's robustness by providing an alternative GEX source.
        - To integrate seamlessly into the existing provider factory, adhering to the project's architecture.

        ## 2. File and Class Structure

        - **New File:** `strategy/gex/ib_provider.py`
        - **Class Name:** `IBProvider`
        - **Inheritance:** The `IBProvider` class must inherit from `strategy.gex.base_provider.BaseGexProvider` and implement all its abstract methods.

        ## 3. `IBProvider` Implementation Details

        ### 3.1. Initialization (`__init__`)

        The constructor will accept the application's `config` object.

        ```python
        # Conceptual signature
        def __init__(self, config: Config):
            # ...
        ```

        - It will be responsible for retrieving the singleton instance of the `IBConnector` from the `ib_client.connector` module to enable interaction with the TWS/Gateway API.

        ### 3.2. Main Method (`get_max_gamma_strike`)

        This method is the core of the provider and must adhere to the `BaseGexProvider` interface.

        ```python
        # Conceptual signature
        async def get_max_gamma_strike(self, symbol: str) -> Optional[float]:
            # ...
        ```

        **Functional Requirements:**

        1.  **Asynchronous Execution:** The method must be `async` to perform non-blocking I/O operations for data fetching.
        2.  **Fetch Option Chain:**
            - Use the `IBConnector` to fetch the option chain for the given underlying `symbol`.
            - The fetch request must be filtered based on parameters from `config.yaml`:
                - `gex.days_to_expiration`: This will control how far out the expiration dates for the options contracts are.
                - `gex.strikes_quantity`: This will control how many strikes around the money are fetched.
            - This includes fetching all available expiration dates and strikes for both calls and puts within the defined filters.
        3.  **Batch Market Data Request:**
            - To ensure efficiency, the provider must request model greeks (specifically Gamma) for all relevant option contracts in a single, batched/concurrent request. It must not loop and request data for each contract sequentially.
        4.  **Calculate Gamma Exposure (GEX):**
            - For each strike price, calculate the total GEX.
            - The GEX for a single option contract is: `GEX = gamma * open_interest * 100`.
            - The total GEX for a strike is the sum of the GEX of all contracts at that strike.
            - **Calculation Logic:** As per the provided analysis, the GEX contribution from both call and put options should be aggregated to find the total magnitude. The specified logic is `call_gex + put_gex`. The implementation must sum the calculated GEX values for calls and puts at each strike.
        5.  **Identify Max Gamma Strike:**
            - After calculating the total GEX for every strike price in the chain, identify the strike with the maximum absolute GEX value.
        6.  **Return Value:**
            - Return the strike price (as a `float`) that has the maximum GEX.
            - Return `None` if the data cannot be fetched or if no options exist for the symbol.

        ## 4. Integration with Provider Factory

        The `strategy/gex/factory.py` file must be updated to integrate the new provider.

        - **Import:** Add `from .ib_provider import IBProvider` to the top of the file.
        - **Update Factory Function:** Modify the `get_gex_provider` function to instantiate `IBProvider` when `config.gex.provider_type` is `1`, replacing the `NotImplementedError`.

        ```python
        # strategy/gex/factory.py - Target state change
        ...
        from .ib_provider import IBProvider # Import the new provider

        def get_gex_provider(config: Config) -> BaseGexProvider:
            provider_type = config.gex.provider_type

            if provider_type == 0:
                return GexbotProvider(config)
            elif provider_type == 1:
                # Now implemented with the refactored code
                return IBProvider(config) 
            elif provider_type == 2:
                return MassiveDataProvider(config)
        ...
        ```

        ## 5. Configuration

        To use this new provider, the `config.yaml` file must be configured as follows. Note the addition of `days_to_expiration` and `strikes_quantity` which are essential for the `IBProvider`.

        ```yaml
        gex:
        provider_type: 1
        days_to_expiration: 30
        strikes_quantity: 20
        # ... other gex settings
        ```

        ## 6. Testing Requirements

        A new test suite must be created to ensure the `IBProvider` functions correctly.

        - **New Test File:** `tests/strategy/gex/test_ib_provider.py`
        - **Test Cases:**
            1.  **Factory Test:** Verify that `get_gex_provider` returns an `IBProvider` instance when `provider_type` is set to `1`.
            2.  **GEX Calculation Test:**
                - Create a unit test that calls the GEX calculation logic directly.
                - Use a predefined set of mock option contracts with known `gamma` and `open_interest`.
                - Assert that the calculated GEX for each strike and the final max gamma strike are correct, specifically verifying the `call_gex + put_gex` summation logic.
            3.  **End-to-End Method Test (`get_max_gamma_strike`):**
                - Mock the `IBConnector` instance and its data-fetching methods.
                - Simulate the IB API returning a sample option chain and market data.
                - Assert that `get_max_gamma_strike` returns the expected strike price.
                - Verify that the implementation attempts to fetch market data concurrently.
            4.  **Error Handling Tests:**
                - Simulate the IB API returning no options for a symbol. Assert the method returns `None`.
                - Simulate API errors during data fetching. Assert that errors are handled gracefully and the method returns `None`.

    Option 3: Use a Dedicated Data Feed - GEX Process type = 2

        # Process Specification: Feed Providers for GEX Calculation (massive)

    This document outlines the technical specification for **Option 3: Use a Dedicated Data Feed** to calculate the strike with the maximum Gamma Exposure (GEX). 
    This process leverages the `massive.com` REST API to acquire the necessary options data in a single, efficient snapshot.

    **Objective:** To identify the single options strike price with the highest absolute concentration of gamma exposure for a given underlying and expiration. 
    This strike level, referred to as `MAX_GAMMA_STRIKE`, serves as a key input for the trade execution logic in Stage 4.

    ---

    ### Step 1: Connection & Authentication

    **Objective:** Establish a secure, authenticated session with the `massive.com` API.

    1.  **Action:** The system will initiate a secure HTTPS connection to the API's base endpoint.
    2.  **Authentication:** Every request must include an `Authorization` header containing the API Key provided by `massive.com`.
        *   **Header Format:** `Authorization: Bearer <YOUR_API_KEY>`
    3.  **Parameters Required (from `config.yaml`):**
        *   `api_key`: The secret API key for the `massive.com` service.
        *   `base_url`: The root URL for the API (e.g., `https://api.massive.com/v1`).
    4.  **Error Handling:**
        *   If a `401 Unauthorized` response is received, the connection attempt has failed due to an invalid API key. The system should log a critical error and halt the GEX calculation process.
        *   Connection timeouts or other network-level errors should trigger a retry mechanism (e.g., retry up to 3 times) before failing.

    ---

    ### Step 2: Data Request (Parameter-Based Snapshot)

    **Objective:** Fetch a complete snapshot of all required options data (quotes, greeks, open interest) in a single API call to minimize latency.

    1.  **Action:** The system will send a single `GET` request to the options chain endpoint.
    2.  **Endpoint:** `/options/chain` (example endpoint based on documentation).
    3.  **Request Parameters:**
        *   `ticker` (string): The underlying symbol (e.g., "SPX").
        *   `days_to_expiration` (integer): The target number of days until the option's expiration.
            The API will use this to select the single, closest expiration date (e.g., a value of `0` targets the 0DTE chain).
        *   `strikes_quantity` (integer): The total number of strikes to retrieve, centered around the current at-the-money (ATM) price. 
            For example, a value of `120` would return the 60 strikes above and 60 strikes below the ATM price.
        *   `fields` (string): A comma-separated list specifying the exact data points to return. This ensures the payload is lean.
            *   **Required Value:** `"greeks,openInterest"`
    4.  **Expected Response (JSON):** The API should return a JSON object containing a list of option contracts for the requested chain. 
        Each element in the list represents a single option (a call or a put) and its associated data.

        ```json
        {
        "expiration": "2026-01-21",
        "options": [
            {
            "strike": 5000.0,
            "type": "call",
            "openInterest": 1520,
            "greeks": { "gamma": 0.0015, "delta": 0.52, ... }
            },
            {
            "strike": 5000.0,
            "type": "put",
            "openInterest": 2100,
            "greeks": { "gamma": 0.0014, "delta": -0.48, ... }
            },
            // ... more contracts
        ]
        }
        ```

    ---

    ### Step 3: Calculate Short and Long Gamma by Strike

    **Objective:** Process the raw data from the API to calculate the total gamma exposure for both calls and puts at each individual strike price.

    1.  **Data Grouping:** The system will first parse the API response and group the options by their `strike` price. Each strike will have an associated call and put contract.
    2.  **Gamma Exposure Calculation:** For each strike `K`, the system calculates the gamma exposure contributed by calls and puts separately.
        *   **Long Gamma (Calls):** This represents the gamma from long call positions.
            *   `Long_Gamma_Exposure_K = Call_Gamma_K * Call_Open_Interest_K * 100`
        *   **Short Gamma (Puts):** This represents the gamma from long put positions. 
            From a market maker's perspective (who is typically short these options), this contributes to their negative gamma position.
            *   `Short_Gamma_Exposure_K = Put_Gamma_K * Put_Open_Interest_K * 100`

        *(Note: The `100` is the standard option multiplier.)*

    ---

    ### Step 4: Aggregation (Absolute Value Summation)

    **Objective:** To determine the total magnitude of gamma risk at each strike, irrespective of whether it comes from calls or puts.

    1.  **Logic:** For every unique strike price `K` processed in the previous step, the system calculates the **Total Gamma Exposure** by summing the exposure from calls and puts.

        `Total_GEX_K = Long_Gamma_Exposure_K + Short_Gamma_Exposure_K`

    2.  **Process:** The system will iterate through all strikes and compute `Total_GEX_K`. 
        The result will be stored in a dictionary (or a similar key-value structure) where the key is the strike price and the value is its calculated total GEX.

        **Example Result:**
        ```
        {
        5000: 22500,  // (Call GEX + Put GEX)
        5010: 18700,
        5020: 31400,  // High concentration
        ...
        }
        ```

    ---

    ### Step 5: Max GEX Identification

    **Objective:** Isolate the single strike price with the highest concentration of total gamma to be used in the trading logic.

    1.  **Operation:** The system will perform a "max" search on the aggregated GEX results from Step 4. It will find the key (strike) corresponding to the largest value (Total GEX).
    2.  **Variable Assignment:** The strike price with the highest `Total_GEX` value is stored in a variable for use in Stage 4.
        *   **Variable Name:** `MAX_GAMMA_STRIKE`

    **Final Output:** The `MAX_GAMMA_STRIKE` variable, holding a single float value (e.g., `5020.0`), is returned by the process. 
        This value is now ready to be consumed by the `Trade Execution` stage to validate trade signals.



**Stage 4: Trade Execution**

# Trade Execution Specification

This document outlines the step-by-step process for trade execution within the bot.

## Process Overview

When the `Engine` calls `OrderManager.place_trade()`, the following sequence of events is triggered:

### 1. Trade Validation (`_make_trade_decision`)

This is the final checkpoint before a trade is initiated. It validates the trade signal against market conditions.

*   **Inputs from Breakout Process:**
    *   `signal_type`: The direction of the signal (e.g., 'Buy', 'Sell').
    *   `spot_price`: The current market price of the underlying asset.
*   **Inputs from GEX Process:**
    *   A tuple containing:
        *   `strike_price`: The relevant strike price from GEX analysis.
        *   `date`: The expiration date for the option.

*   **Execution Conditions:** The decision to execute a specific option type is based on the following logic:

| Signal Type | Condition                 | Action           |
|-------------|---------------------------|------------------|
| Buy         | `strike_price > spot_price` | Long Call @ ATM  |
| Buy         | `strike_price < spot_price` | Long Put @ ATM   |
| Sell        | `strike_price < spot_price` | Long Put @ ATM   |
| Sell        | `strike_price > spot_price` | Long Call @ ATM  |

### 2. ATM Strike Calculation (`_get_atm_strike`)

If the trade is validated, this step calculates the At-The-Money (ATM) strike price.

*   **Logic:** The `spot_price` is rounded to the nearest available strike price. The rounding direction might be specified as "above", but for ATM it should be the closest. *Initial implementation will round to the nearest strike above.*

### 3. Option Contract Definition (`_create_option_contract`)

This step constructs the official IBKR `Contract` object required for placing an order.

*   **Inputs:**
    *   ATM Strike Price (from step 2).
    *   Trade Direction (Call/Put, determined in step 1).
    *   Expiration Date (from GEX process).
*   **Output:** An `ibapi.contract.Contract` object fully defined for the trade.

### 4. Fetch Option Price

Before submitting the order, the system must fetch the current market price of the specific option contract defined in the previous step.

*   **Action:** Request market data for the created `Contract` object form ibkr.
*   **Output:** The current bid/ask or last traded price of the option.

### 5. Place Opening Order

This two-part step creates and submits the opening order to IBKR.

1.  **Create Opening Order:** An `ibapi.order.Order` object is created. This will specify order type (e.g., Market, Limit), quantity, and action (BUY).
2.  **Submit Opening Order:** The `Contract` and `Order` objects are submitted to IBKR via the API.

### 6. Post-Trade Management

Once the trade is open and the execution price is confirmed, the focus shifts to managing the position using a server-side bracket order that can be dynamically modified.

*   **Initial Bracket Order Submission:**
    1.  **Calculate TP/SL Prices:** Based on the actual execution price of the option, calculate the absolute price levels for the Take Profit (TP) and Stop Loss (SL) using percentage values from `config.yaml`.
    2.  **Structure Bracket Orders:** Create two `Order` objects:
        *   A `LMT` (Limit) order for the Take Profit price.
        *   A `STP` (Stop) order for the Stop Loss price.
    3.  **Submit as Attached Bracket:** Submit these two orders attached to the parent opening order, forming a single, cohesive bracket order on the broker's server. This ensures the position is protected even if the bot disconnects.

*   **Dynamic Trailing Stop Loss via Order Modification:**
    *   **Monitoring:** The system will monitor the position's status and current market price every 5 seconds.
    *   **Trailing Condition:** The trailing stop loss logic is activated if the trade meets the following criteria:
        *   Profit is positive and greater than the `activation_profit_pct` from `config.yaml`.
        *   Profit is less than the pre-defined `take_profit_pct` from `config.yaml`.
    *   **Trailing Action (Order Modification):**
        *   Instead of cancelling the order, the system will **modify** the existing Stop Loss order.
        *   This is achieved by submitting a new order request using the **same `orderId`** as the original Stop Loss order, but with an updated stop price.
        *   The new stop price will be calculated based on the `trail_pct` parameter defined in `config.yaml`.
        *   This action updates the Stop Loss on the broker's server without affecting the Take Profit order, thus preserving the integrity of the bracket.

## Configuration Parameters (`config.yaml`)

The following parameters will be required in `config.yaml` to support this process:

```yaml
trade_management:
  take_profit_pct: 0.50  # e.g., 50%
  stop_loss_pct: 0.20    # e.g., 20%
  trailing_stop:
    activation_profit_pct: 0.10 # e.g., 10%
    trail_pct: 0.10             # e.g., Trail by 10%