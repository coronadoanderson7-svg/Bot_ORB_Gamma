# Plan for Implementing IBProvider for GEX Calculation

This document outlines the step-by-step plan to implement the `IBProvider`, a new GEX data provider that sources data directly from Interactive Brokers. The plan is designed to ensure seamless integration with the existing bot architecture.

## 1. Foundational Setup

-   **Create File:** Create the new provider file at `strategy/gex/ib_provider.py`.
-   **Create Class Skeleton:** Inside the new file, define the `IBProvider` class.
    -   It must inherit from `strategy.gex.base_provider.BaseGexProvider`.
    -   Create a basic `__init__` method to accept the `config` object.
    -   Create an empty, `async` `get_max_gamma_strike` method that matches the base class signature and returns `None` as a placeholder.

## 2. Configuration and Integration

This step ensures the provider is correctly recognized and configured within the application.

-   **Verify Config Model:** Check `models/data_models.py` to ensure the `GexConfig` class includes the new fields: `days_to_expiration` and `strikes_quantity`. If not, add them. This is critical for the configuration to be loaded correctly.
-   **Update Provider Factory:** Modify `strategy/gex/factory.py`:
    -   Import `IBProvider` from `.ib_provider`.
    -   In the `get_gex_provider` function, replace the `NotImplementedError` for `provider_type == 1` with `return IBProvider(config)`.

## 3. Test Suite Scaffolding

-   **Create Test File:** Create `tests/strategy/gex/test_ib_provider.py`.
-   **Implement Factory Test:** Add a test to verify that `get_gex_provider` returns a valid `IBProvider` instance when the config `provider_type` is set to `1`. This confirms the integration from step 2 is working.

## 4. Core Logic Implementation (`get_max_gamma_strike`)

This is the main implementation phase within `strategy/gex/ib_provider.py`.

-   **Initialize Connector:** In the `__init__` method, retrieve the singleton instance of the `IBConnector`.
-   **Implement Data Fetching:**
    -   Use the `IBConnector` instance to fetch the option chain for the given symbol.
    -   The request must be filtered using `config.gex.days_to_expiration` and `config.gex.strikes_quantity`.
    -   Implement the mechanism to request model greeks (Gamma) for all relevant option contracts concurrently to ensure efficiency.
-   **Implement GEX Calculation:**
    -   Implement the logic to calculate total GEX for each strike: `GEX = (gamma * open_interest * 100)`.
    -   The total GEX for a strike is the sum of GEX for all associated call and put contracts (`call_gex + put_gex`).
-   **Identify and Return Max GEX Strike:**
    -   Implement the logic to find the strike with the maximum absolute GEX value.
    -   Ensure the method's return type (`Optional[float]`) strictly adheres to the `BaseGexProvider` interface to guarantee compatibility with consumer modules like `GexAnalyzer`.
-   **Implement Error Handling:** Gracefully handle scenarios where the API returns no options or an error occurs, ensuring `None` is returned.

## 5. Comprehensive Testing

Expand the test suite in `tests/strategy/gex/test_ib_provider.py` to ensure robustness.

-   **Mock Dependencies:** All tests will use a mocked `IBConnector` and a mock `Config` object to isolate the `IBProvider` and control test conditions.
-   **End-to-End Method Test:** Test the `get_max_gamma_strike` method by simulating API responses from the mocked `IBConnector` and asserting that the correct max gamma strike is returned.
-   **Calculation Logic Unit Test:** Write a focused unit test for the GEX calculation logic using a predefined, static set of option data to verify its correctness independently.
-   **Error Handling Tests:** Simulate API errors and empty responses from the mock connector to verify the provider returns `None` as expected.

## 6. System Integration Review

This final phase verifies that the new provider works correctly within the live application flow.

-   **Trace Data Flow:** Mentally (or with a debugger) trace the call stack from `main.py` -> `TradingEngine` -> `GexAnalyzer` (or other consumer) -> `get_gex_provider` -> `IBProvider.get_max_gamma_strike`.
-   **Verify Consumer Logic:** Review the code in `GexAnalyzer` (or the module that uses the GEX provider) to confirm it correctly handles the `float` or `None` output without errors.
-   **Dry Run:** After implementation, configure `config.yaml` to use `provider_type: 1` and run the application to ensure no runtime `AttributeError` or `TypeError` exceptions occur at the integration points.
