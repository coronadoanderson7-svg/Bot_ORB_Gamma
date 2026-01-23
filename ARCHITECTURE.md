# Proposed Project Architecture

This document outlines the refined architecture for the trading bot. The structure is designed around principles of modularity, scalability, and separation of concerns, enabling robust and maintainable development.

## Core Principles

*   **Modularity:** Each distinct function of the bot (e.g., connection, strategy logic, execution) is isolated in its own package or module.
*   **Decoupling:** The `core/engine.py` acts as an orchestrator and is decoupled from the specific implementation details of the strategies it runs.
*   **Extensibility:** The architecture uses design patterns (like the Strategy Pattern for GEX) that allow for new features or data sources to be added with minimal changes to existing code.

## Directory Structure

```
c:\Users\ander\PythonProjects\Bot_ORB_Gamma\
│
├── core\
│   ├── __init__.py
│   ├── engine.py             # Main orchestrator and state machine
│   ├── config_loader.py      # Loads and validates config.yaml
│   └── logging_setup.py      # Configures logging for the entire app
│
├── ib_client\
│   ├── __init__.py
│   ├── connector.py          # High-level interface for connecting and making requests
│   ├── wrapper.py            # EWrapper implementation (handles incoming data)
│   └── client.py             # EClient implementation (sends requests)
│
├── strategy\
│   ├── __init__.py
│   ├── opening_range.py      # Logic for Stage 1
│   ├── breakout.py           # Logic for Stage 2
│   ├── gex_analyzer.py       # Analyzes GEX data
│   └── gex\                  # Stage 3: GEX logic using a Strategy Pattern
│       ├── __init__.py
│       ├── base_provider.py    # Abstract interface for all GEX providers
│       ├── factory.py          # Creates the correct provider based on config
│       ├── gexbot_provider.py  # Implements "Option 1" (gexbot.com API)
│       ├── ib_provider.py      # Implements "Option 2" (calculates GEX via IBKR)
│       ├── massive_data_provider.py # Implements "Option 3" (massive.com API)
│       └── models.py           # Pydantic models for API responses
│
├── execution\
│   ├── __init__.py
│   └── order_manager.py      # Logic for Stage 4 (placing and managing orders)
│
├── models\
│   ├── __init__.py
│   └── data_models.py        # Pydantic or Dataclass models (Bar, Signal, Order, etc.)
│
├── tests\
│   ├── __init__.py
│   ├── core\
│   │   ├── __init__.py
│   │   ├── test_config_loader.py
│   │   └── test_engine.py
│   ├── execution\
│   │   ├── __init__.py
│   │   └── test_order_manager.py
│   └── strategy\
│       ├── __init__.py
│       ├── test_breakout.py
│       ├── test_gex_analyzer.py
│       ├── test_opening_range.py
│       └── gex\
│           ├── __init__.py
│           ├── test_factory.py
│           ├── test_gexbot_provider.py
│           ├── test_ib_provider.py # Tests for the IB provider
│           └── test_massive_data_provider.py
│
├── main.py                   # Application entry point
├── config.yaml               # Your existing configuration file
├── Requirements.txt          # Your existing requirements file
├── ARCHITECTURE.md           # This file
└── Project Summary.md        # Your existing project summary
```
