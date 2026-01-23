# GEX Module Development Plan

This document provides a detailed, step-by-step plan for developing the Gamma Exposure (GEX) analysis module (Stage 3). The plan synthesizes the requirements from the `Project Summary.md` and the structure defined in `ARCHITECTURE.md`.

## 1. Objective

The primary objective is to create a modular and extensible system for calculating the strike price with the maximum gamma exposure (`MAX_GAMMA_STRIKE`). The system will use a Strategy design pattern to allow for different GEX data providers to be selected via configuration.

## 2. Configuration Setup (`config.yaml`)

The first step is to amend the existing `gex` section in `config.yaml` to include provider selection and their specific settings.

- **Action:** Modify the `gex` section in `config.yaml`.

```yaml
# c:\Users\ander\PythonProjects\Bot_OR_B_Gamma\config.yaml

# ... existing configuration ...

# ==============================================================================
# Stage 3: Gamma Exposure (GEX) Analysis
# ==============================================================================
gex:
  days_to_expiration: 0       # 0 for 0DTE, 1 for 1DTE, etc.
  strikes_quantity: 120       # Total number of strikes to fetch (for providers that need it)
  option_multiplier: 100      # Standard multiplier for options contracts

  # --- Provider Selection ---
  # GEX Process Type: 0 = gexbot, 1 = microservice (not implemented), 2 = massive_data
  provider_type: 0

  # --- Provider-Specific Settings ---
  providers:
    gexbot:
      api_key: "YOUR_GEXBOT_API_KEY"
      base_url: "https://api.gexbot.com/v1"
    massive_data:
      api_key: "YOUR_MASSIVE_DATA_API_KEY"
      base_url: "https://api.massive.com/v1" # Example URL
```

## 3. Architectural Implementation (`strategy/gex/`)

This phase involves creating the directory and files required by the Strategy pattern, as outlined in the architecture.

### Step 3.1: Create Directory and `__init__.py`

- **Action:** Create the `strategy/gex/` directory.
- **Action:** Create an empty `strategy/gex/__init__.py` file to mark it as a Python package.

### Step 3.2: Pydantic Models (`strategy/gex/models.py`)

- **Action:** Create the `strategy/gex/models.py` file.
- **Objective:** Define Pydantic models to validate and parse the JSON responses from the different API providers. This ensures data consistency.

```python
# strategy/gex/models.py

from pydantic import BaseModel, Field
from typing import List

# --- Models for Gexbot (Option 1) ---

class GexbotStrikeData(BaseModel):
    strike: float
    long_gamma: float
    short_gamma: float

class GexbotResponse(BaseModel):
    success: bool
    data: List[GexbotStrikeData]

# --- Models for Massive Data (Option 3) ---

class MassiveDataGreeks(BaseModel):
    gamma: float

class MassiveDataOption(BaseModel):
    strike: float
    type: str  # 'call' or 'put'
    open_interest: int = Field(alias='openInterest')
    greeks: MassiveDataGreeks

class MassiveDataResponse(BaseModel):
    expiration: str
    options: List[MassiveDataOption]
```

### Step 3.3: Abstract Base Provider (`strategy/gex/base_provider.py`)

- **Action:** Create the `strategy/gex/base_provider.py` file.
- **Objective:** Define the abstract interface that all GEX providers must implement. This is the contract for the Strategy pattern.

```python
# strategy/gex/base_provider.py

from abc import ABC, abstractmethod
from core.config_loader import Config

class BaseGexProvider(ABC):
    """
    Abstract base class for all GEX data providers.
    """
    def __init__(self, config: Config):
        self.config = config

    @abstractmethod
    def get_max_gamma_strike(self, ticker: str) -> float:
        """
        Fetches data from the provider, calculates total gamma exposure for each strike,
        and returns the strike with the highest concentration.

        Args:
            ticker (str): The underlying symbol (e.g., 'SPX').

        Returns:
            float: The strike price with the maximum gamma exposure.
        """
        pass
```

### Step 3.4: Gexbot Provider (`strategy/gex/gexbot_provider.py`)

- **Action:** Create the `strategy/gex/gexbot_provider.py` file.
- **Objective:** Implement the `BaseGexProvider` for **Option 1 (gexbot.com)**.

**Implementation Steps:**
1.  **Initialize:** The constructor will receive the global `config` object.
2.  **Implement `get_max_gamma_strike`:**
    a. **Calculate Expiration Date:** Use `datetime` and `timedelta` with `self.config.gex.days_to_expiration` to calculate the target expiration date string in `YYYY-MM-DD` format. please take into account that the parameter days_to_expiration: 0 for 0DTE, 1 for 1DTE, etc.
    b. **Connect & Fetch:** Make a `GET` request to the `/gex/distribution` endpoint. Use the `base_url` and `api_key` from `self.config.gex.providers.gexbot`. Pass the `ticker` and calculated expiration date as query parameters.
    c. **Error Handling:** Check for non-200 status codes and raise an exception.
    d. **Parse & Aggregate:** Parse the response with `GexbotResponse` model. For each strike, calculate `Total_GEX = abs(short_gamma) + abs(long_gamma)`.
    e. **Find Max & Return:** Find and return the strike with the highest `Total_GEX`.

### Step 3.5: Massive Data Provider (`strategy/gex/massive_data_provider.py`)

- **Action:** Create the `strategy/gex/massive_data_provider.py` file.
- **Objective:** Implement the `BaseGexProvider` for **Option 3 (massive.com)**.

**Implementation Steps:**
1.  **Initialize:** The constructor will receive the global `config` object.
2.  **Implement `get_max_gamma_strike`:**
    a. **Connect & Fetch:** Make a `GET` request to the `/options/chain` endpoint. Use the `base_url` and `api_key` from `self.config.gex.providers.massive_data`. Pass parameters from the config: `ticker`, `days_to_expiration=self.config.gex.days_to_expiration`, and `strikes_quantity=self.config.gex.strikes_quantity`.
    b. **Error Handling:** Check for non-200 status codes and raise an exception.
    c. **Parse Data:** Use the `MassiveDataResponse` model to parse the JSON.
    d. **Calculate Gamma Exposure:** For each option, calculate `gamma * open_interest * self.config.gex.option_multiplier` and aggregate the results per strike (summing calls and puts).
    e. **Find Max & Return:** Find and return the strike with the highest total gamma exposure.

### Step 3.6: Provider Factory (`strategy/gex/factory.py`)

- **Action:** Create the `strategy/gex/factory.py` file.
- **Objective:** Create a factory function that selects and instantiates the correct GEX provider.

```python
# strategy/gex/factory.py

from core.config_loader import Config
from .base_provider import BaseGexProvider
from .gexbot_provider import GexbotProvider
from .massive_data_provider import MassiveDataProvider

def get_gex_provider(config: Config) -> BaseGexProvider:
    """
    Factory function to get the appropriate GEX provider based on config.

    Args:
        config: The application's configuration object.

    Returns:
        An instance of a class that implements BaseGexProvider.
    """
    provider_type = config.gex.provider_type

    if provider_type == 0:
        return GexbotProvider(config)
    elif provider_type == 2:
        return MassiveDataProvider(config)
    elif provider_type == 1:
        raise NotImplementedError("GEX Microservice provider is not yet implemented.")
    else:
        raise ValueError(f"Invalid provider_type in config: {provider_type}")
```

## 4. Integration with Core Engine (`core/engine.py`)

- **Action:** Modify `core/engine.py` to use the GEX factory.
- **Objective:** The engine will use the factory to get the GEX provider and call it during Stage 3.

**Example Snippet for `core/engine.py`:**
```python
# ... inside the engine's main loop or state machine ...

# STAGE 3: GEX ANALYSIS
from strategy.gex.factory import get_gex_provider

# Assume 'self.config' is the loaded configuration object
gex_provider = get_gex_provider(self.config)

# Fetch the max gamma strike
try:
    max_gamma_strike = gex_provider.get_max_gamma_strike(
        ticker=self.config.instrument.ticker
    )
    self.logger.info(f"Max Gamma Strike identified: {max_gamma_strike}")

except Exception as e:
    self.logger.error(f"GEX analysis failed: {e}")
    # Decide how to proceed: halt or trade without GEX data?
    # ...

# The 'max_gamma_strike' variable is now available for Stage 4
# ...
```

## 5. Testing Strategy

- **Objective:** Create unit tests to ensure each component works as expected.
- **Actions:**
    1.  Create `tests/strategy/gex/` directory.
    2.  Create `tests/strategy/gex/test_gexbot_provider.py` and `tests/strategy/gex/test_massive_data_provider.py`.
    3.  **Mock API Calls:** Use `pytest-mock` or `unittest.mock` to mock `requests.get`.
    4.  **Test Logic:** For each provider, write tests to verify:
        - Correct calculation of total gamma exposure using parameters from a mock config object.
        - Correct identification of the max gamma strike from sample data.
        - Proper handling of API errors.
    5.  Create `tests/strategy/gex/test_factory.py` to ensure the factory returns the correct provider instance.

This plan provides a clear roadmap for implementing the GEX module in a clean, maintainable, and testable way.
