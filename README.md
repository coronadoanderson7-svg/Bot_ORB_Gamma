# Bot_ORB_Gamma (V4)

> A modular, Python-based algorithmic trading bot that combines **Opening Range Breakout (ORB)** strategies with **Gamma Exposure (GEX)** analysis for automated intraday trading via Interactive Brokers.

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Trading Strategy](#trading-strategy)
- [Running Tests](#running-tests)
- [Documentation](#documentation)
- [Disclaimer](#disclaimer)

---

## Overview

Bot_ORB_Gamma is a quantitative trading system engineered for automated intraday operations on the US equities and options markets. It executes a four-stage pipeline:

1. **Opening Range Detection** — Captures the high/low of the first N minutes after market open.
2. **Breakout Signaling** — Monitors real-time bars for a confirmed directional breakout.
3. **GEX Confirmation** — Filters or sizes trades using Gamma Exposure data from a configurable provider.
4. **Trade Execution & Management** — Places and actively manages orders via the IBKR API, including take-profit, stop-loss, and trailing stop logic.

The bot connects to Interactive Brokers through `ib_async` and is designed for **paper trading by default** before going live.

---

## Features

- **ORB Engine** — Uses candle high/low (not open/close) to define range thresholds for precise breakout detection.
- **GEX Analysis** — Integrates real-time gamma calculations to contextualize volatility and optimize entries, particularly for 0DTE and 1DTE options.
- **IBKR Integration** — Asynchronous, event-driven connection to Interactive Brokers (TWS or IB Gateway) via `ib_async`.
- **Configurable Pipeline** — All parameters — instrument, timing, GEX provider, order types, risk levels — are controlled through a single `config.yaml`.
- **Pluggable GEX Providers** — Supports multiple data providers (`gexbot`, `massive_data`) selectable at runtime.
- **Risk Management** — Built-in take-profit %, stop-loss %, and trailing stop with configurable activation thresholds.
- **Structured Logging** — Full trade and system logging via `loguru` to file and console.
- **Test Suite** — `pytest`-based tests for strategy logic and API interactions with mock support.

---

## Project Structure

```
Bot_ORB_Gamma/
├── core/               # Shared utilities, global config loading, base classes
├── execution/          # Order lifecycle management, position tracking, order routing
├── ib_client/          # Async IBKR connection, event loops, market data streaming
├── models/             # Data structures and statistical modeling components
├── strategy/           # ORB detection, breakout signaling, GEX integration logic
├── tests/              # pytest test suite
├── config.yaml         # Main configuration file
├── main.py             # Entry point
├── Requirements.txt    # Python dependencies
└── ARCHITECTURE.md     # System design reference
```

---

## Prerequisites

- Python **3.10+**
- **Interactive Brokers** account (paper or live)
- **Trader Workstation (TWS)** or **IB Gateway** running locally
  - Default TWS port: `7497`
  - Default IB Gateway port: `4002`
- API access enabled in TWS/Gateway settings
- A GEX data provider API key (if using `gexbot` or `massive_data`)

---

## Installation

```bash
# 1. Clone the repository
git clone https://github.com/coronadoanderson7-svg/Bot_ORB_Gamma.git
cd Bot_ORB_Gamma

# 2. Create and activate a virtual environment (recommended)
python -m venv venv
source venv/bin/activate      # macOS/Linux
venv\Scripts\activate         # Windows

# 3. Install dependencies
pip install -r Requirements.txt
```

---

## Configuration

All settings live in `config.yaml`. Key sections:

```yaml
# IBKR connection
connection:
  host: 127.0.0.1
  port: 4002        # TWS: 7497 | IB Gateway: 4002
  client_id: 1

# Account mode
account:
  type: "paper"     # "paper" or "live"
  code: ""          # Your IB account code, e.g. "U1234567"

# Instrument
instrument:
  ticker: "SPX"
  exchange: "CBOE"
  currency: "USD"
  exchange_timezone: "America/New_York"

# Opening range window
opening_range:
  market_open_time: "09:30:00"
  duration_minutes: 15

# GEX provider
gex:
  days_to_expiration: 0       # 0 = 0DTE, 1 = 1DTE
  provider_type: 1            # 0 = gexbot, 2 = massive_data
  providers:
    gexbot:
      api_key: "YOUR_GEXBOT_API_KEY"

# Risk management
trade_management:
  take_profit_pct: 40
  stop_loss_pct: 50
  trailing_stop:
    activation_profit_pct: 10
    trail_pct: 16
```

> **Never commit real API keys or account credentials to version control.** Use environment variables or a `.env` file (git-ignored) to inject secrets at runtime.

---

## Usage

1. Start TWS or IB Gateway and ensure API connections are enabled.
2. Update `config.yaml` with your connection details and desired parameters.
3. Run the bot:

```bash
python main.py
```

Logs are written to `trading_bot.log` (configurable in `config.yaml`). The bot will wait for market open, build the opening range, then begin monitoring for breakouts.

---

## Trading Strategy

The bot follows a four-stage intraday pipeline:

| Stage | Description |
|-------|-------------|
| **1 — Opening Range** | Captures the high and low of the first N minutes after market open (default: 15 min). |
| **2 — Breakout Detection** | Monitors subsequent candles; triggers a signal when price closes above/below the range. |
| **3 — GEX Confirmation** | Cross-references the breakout direction with gamma exposure levels to filter noise. |
| **4 — Execution** | Submits entry (limit), take-profit (limit), and stop-loss (stop) orders; manages trailing stop once activation threshold is reached. |

---

## Running Tests

```bash
pytest tests/
```

The test suite uses `pytest-mock` to simulate IBKR API responses without requiring a live connection.

---

## Documentation

Additional reference documents are included in the repository:

| File | Contents |
|------|----------|
| `ARCHITECTURE.md` | Structural design overview and module responsibilities |
| `GEX_Development_Plan.md` | Gamma exposure math, data pipeline specifications |
| `IBKR_Requirements.md` | IBKR API prerequisites, port configuration, connection setup |
| `plan_trade_execution.md` | Trade lifecycle logic, order fill management |
| `roadmap_Program.md` | Development roadmap and planned features |

---

## Disclaimer

> **This software is provided for educational and research purposes only.**
> Algorithmic trading involves significant financial risk. Past performance does not guarantee future results. Use paper trading to validate the strategy before deploying real capital. The authors assume no responsibility for any financial losses incurred through use of this software.
