"""
Loads, validates, and stores all configuration parameters from config.yaml.

This module uses Pydantic to define a strict schema for the configuration file.
This ensures that all required parameters are present and correctly typed before the
application starts, preventing a large class of potential runtime errors.

The loaded and validated configuration is stored in a singleton `APP_CONFIG`
which can be imported and used by any other module in the application.
"""

import yaml
from pydantic import BaseModel, Field, FilePath
from typing import Literal

# --- Pydantic Models for Configuration Schema ---

class ConnectionConfig(BaseModel):
    """Schema for IB API connection settings."""
    host: str
    port: int
    client_id: int = Field(..., ge=0)

class AccountConfig(BaseModel):
    """Schema for account settings."""
    type: Literal["paper", "live"]
    code: str

class InstrumentConfig(BaseModel):
    """Schema for trading instrument details."""
    ticker: str
    exchange: str
    currency: str
    exchange_timezone: str

class OpeningRangeConfig(BaseModel):
    """Schema for Opening Range stage."""
    market_open_time: str
    duration_minutes: int = Field(..., gt=0)
    bar_size: str

class BreakoutConfig(BaseModel):
    """Schema for Breakout Detection stage."""
    bar_size_seconds: int = Field(..., gt=0)

class GEXConfig(BaseModel):
    """Schema for Gamma Exposure (GEX) Analysis stage."""
    days_to_expiration: int = Field(..., ge=0)
    strikes_quantity: int = Field(..., gt=0)
    option_multiplier: int

class OrderDefaultsConfig(BaseModel):
    """Schema for default order types."""
    entry_order_type: str
    tp_order_type: str
    sl_order_type: str

class TradeExecutionConfig(BaseModel):
    """Schema for Trade Execution stage."""
    take_profit_percentage: float = Field(..., gt=0)
    stop_loss_percentage: float = Field(..., gt=0)
    order_defaults: OrderDefaultsConfig

class LoggingConfig(BaseModel):
    """Schema for logging settings."""
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    log_file: str

class AppConfig(BaseModel):
    """Root schema for the entire config.yaml file."""
    connection: ConnectionConfig
    account: AccountConfig
    instrument: InstrumentConfig
    opening_range: OpeningRangeConfig
    breakout: BreakoutConfig
    gex: GEXConfig
    trade_execution: TradeExecutionConfig
    logging: LoggingConfig


def load_config(config_path: str = "config.yaml") -> AppConfig:
    """
    Loads configuration from a YAML file, validates it against the AppConfig schema,
    and returns a validated configuration object.

    Args:
        config_path: The path to the configuration YAML file.

    Returns:
        An instance of AppConfig with the loaded and validated settings.
        
    Raises:
        FileNotFoundError: If the config file does not exist.
        ValidationError: If the config file does not match the schema.
    """
    try:
        with open(config_path, 'r') as f:
            config_data = yaml.safe_load(f)
        
        validated_config = AppConfig(**config_data)
        return validated_config

    except FileNotFoundError:
        print(f"ERROR: Configuration file not found at '{config_path}'")
        raise
    except Exception as e:
        print(f"ERROR: Failed to load or validate configuration: {e}")
        raise

# --- Singleton Config Object ---
# Load the configuration once when the module is first imported.
# Other modules can then simply `from core.config_loader import APP_CONFIG`.
APP_CONFIG = load_config()
