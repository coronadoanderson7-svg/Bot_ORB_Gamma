# Bot_ORB_Gamma (V4)

## Overview
Bot_ORB_Gamma is a modular algorithmic trading bot engineered for automated financial market operations. Built in Python, this system specializes in executing quantitative Opening Range Breakout (ORB) strategies while dynamically analyzing Gamma Exposure (GEX) to optimize trade entries and manage intraday risk. 

## Key Features
* **Opening Range Breakout (ORB) Engine:** Robust breakout detection that rigorously utilizes the high and low prices of a candle (rather than open and close) to identify precise range thresholds and trigger directional signals. 
* **Gamma Exposure (GEX) Analysis:** Integrates real-time gamma calculations to contextualize market volatility, price action, and tail risk—particularly optimized for 0DTE and 1DTE options.
* **Interactive Brokers Integration:** Direct, robust connectivity to the IBKR API (utilizing `ib_async`) for market data streaming and rapid trade execution.
* **Modular Architecture:** Strict separation of concerns across client connections, strategy logic, and order execution to allow for scalable financial engineering and straightforward testing.

## Project Structure
The repository is organized to support a robust V4 modular design:

* `ib_client/` - Manages the asynchronous connection, event loops, and data streaming with the Interactive Brokers API.
* `strategy/` - Contains the quantitative trading logic, including ORB detection and first-candle breakout signaling.
* `models/` - Data structures and statistical modeling components.
* `execution/` - Handles the lifecycle of trades, position management, and order routing.
* `core/` - Foundational utilities, shared methods, and global configurations.
* `tests/` - Testing suite for validating strategy logic and API interactions without risking capital.

## Documentation Reference
For deeper insights into the bot's system design and development roadmap, refer to the included documentation:
* `ARCHITECTURE.md` - Detailed overview of the system's structural design.
* `GEX_Development_Plan.md` - Specifications and mathematics for the gamma exposure integration.
* `IBKR_Requirements.md` - API prerequisites, port configurations, and connection guidelines.
* `plan_trade_execution.md` - Logic for managing active positions and dynamic order fills.

## Installation & Setup

1. **Clone the repository:**
   ```bash
   git clone [https://github.com/coronadoanderson7-svg/Bot_ORB_Gamma.git](https://github.com/coronadoanderson7-svg/Bot_ORB_Gamma.git)
   cd Bot_ORB_Gamma
