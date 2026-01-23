Here is a roadmap of the program's processes:

1.	Initialization (main.py): The application starts by creating an instance of the Engine.
2.	Configuration (core/config_loader.py, config.yaml): The Engine and all other modules are configured via a single config.yaml file, which is validated against a Pydantic schema at startup.
3.	State Machine Execution (core/engine.py): The Engine acts as a state machine, progressing through the following states:
    3.1. CONNECTING: Connects to the Interactive Brokers TWS/Gateway using connection details from the config. This is handled by the ib_client module.
    3.2. GETTING_OPENING_RANGE: After the market opens, it requests historical bar data for a configured duration (e.g., 30 mins). The OpeningRangeStrategy processes these bars to find the session's high and low.
    3.3. MONITORING_BREAKOUT: The Engine then requests real-time bar data. The BreakoutStrategy aggregates these bars into larger candles (e.g., 5-min) and checks if a candle forms entirely above the opening range high (a BUY signal) or below the low (a SELL signal).
    3.4. ANALYZING_GEX: Upon receiving a BUY or SELL signal, the Engine invokes a GEX provider to find the option strike with the highest gamma exposure. The specific provider is chosen via a factory based on the `provider_type` parameter in `config.yaml`. The available providers are:
	*   `0`: GexbotProvider - Uses the third-party gexbot.com REST API.
	*   `1`: IBProvider - Calculates GEX by fetching option chain and greek data directly from Interactive Brokers.
	*   `2`: MassiveDataProvider - Uses a dedicated data feed from massive.com.
    3.5. PENDING_TRADE_EXECUTION: The Engine calls the OrderManager with the signal and GEX data. The OrderManager is responsible for constructing and placing the appropriate option trades (e.g., buying a call or put) with associated take-profit and stop-loss orders.
    3.6. SHUTDOWN: After placing the trade, the bot currently shuts down.

