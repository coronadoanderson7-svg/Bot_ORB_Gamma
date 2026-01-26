import pytest
import yaml
from pydantic import ValidationError
from core.config_loader import load_config, AppConfig

@pytest.fixture
def valid_config_file(tmp_path):
    """Creates a temporary valid config file for testing."""
    config_data = {
        "connection": {"host": "127.0.0.1", "port": 7497, "client_id": 1},
        "account": {"type": "paper", "code": "U12345"},
        "instrument": {"ticker": "SPX", "exchange": "CBOE", "currency": "USD", "exchange_timezone": "America/New_York"},
        "opening_range": {
            "market_open_time": "09:30:00", 
            "duration_minutes": 30, 
            "bar_size": "1 min",
            "wait_buffer_seconds": 5,
            "historical_data_timeout_seconds": 20
        },
        "breakout": {"bar_size_seconds": 300},
        "gex": {"days_to_expiration": 0, "strikes_quantity": 120, "option_multiplier": 100},
        "trade_execution": {
            "order_defaults": {
                "entry_order_type": "LMT",
                "tp_order_type": "LMT",
                "sl_order_type": "STP"
            }
        },
        "trade_management": {
            "take_profit_pct": 0.50,
            "stop_loss_pct": 0.20,
            "trailing_stop": {
                "activation_profit_pct": 0.10,
                "trail_pct": 0.10
            }
        },
        "logging": {"log_level": "INFO", "log_file": "test.log"}
    }
    config_file = tmp_path / "config.yaml"
    with open(config_file, 'w') as f:
        yaml.dump(config_data, f)
    return str(config_file)

@pytest.fixture
def invalid_config_file(tmp_path):
    """Creates a temporary invalid config file (missing a required field)."""
    config_data = {
        "connection": {"host": "127.0.0.1", "port": 7497}, # Missing client_id
        "account": {"type": "paper", "code": "U12345"},
        "instrument": {"ticker": "SPX", "exchange": "CBOE", "currency": "USD", "exchange_timezone": "America/New_York"},
        "opening_range": {
            "market_open_time": "09:30:00", 
            "duration_minutes": 30, 
            "bar_size": "1 min",
            "wait_buffer_seconds": 5,
            "historical_data_timeout_seconds": 20
        },
        "breakout": {"bar_size_seconds": 300},
        "gex": {"days_to_expiration": 0, "strikes_quantity": 120, "option_multiplier": 100},
        "trade_execution": {
            "order_defaults": {
                "entry_order_type": "LMT",
                "tp_order_type": "LMT",
                "sl_order_type": "STP"
            }
        },
        "trade_management": {
            "take_profit_pct": 0.50,
            "stop_loss_pct": 0.20,
            "trailing_stop": {
                "activation_profit_pct": 0.10,
                "trail_pct": 0.10
            }
        },
        "logging": {"log_level": "INFO", "log_file": "test.log"}
    }
    config_file = tmp_path / "config.yaml"
    with open(config_file, 'w') as f:
        yaml.dump(config_data, f)
    return str(config_file)

def test_load_valid_config(valid_config_file):
    """
    Tests that a valid config file is loaded correctly into an AppConfig object.
    """
    # Act
    config = load_config(valid_config_file)

    # Assert
    assert isinstance(config, AppConfig)
    assert config.connection.host == "127.0.0.1"
    assert config.instrument.ticker == "SPX"
    assert config.trade_management.take_profit_pct == 0.50
    assert config.trade_management.trailing_stop.trail_pct == 0.10

def test_load_invalid_config_raises_error(invalid_config_file):
    """
    Tests that loading an invalid config file raises a ValidationError.
    """
    # Act & Assert
    with pytest.raises(ValidationError):
        load_config(invalid_config_file)

def test_load_nonexistent_config_raises_error():
    """
    Tests that trying to load a nonexistent config file raises a FileNotFoundError.
    """
    # Act & Assert
    with pytest.raises(FileNotFoundError):
        load_config("nonexistent_file.yaml")

def test_trailing_stop_validation():
    """
    Tests that the trailing stop configuration values are correctly validated.
    """
    from core.config_loader import TrailingStopConfig
    
    # Test valid data
    valid_data = {"activation_profit_pct": 0.1, "trail_pct": 0.1}
    ts_config = TrailingStopConfig(**valid_data)
    assert ts_config.activation_profit_pct == 0.1
    assert ts_config.trail_pct == 0.1
    
    # Test invalid data (values <= 0)
    with pytest.raises(ValidationError):
        TrailingStopConfig(activation_profit_pct=0, trail_pct=0.1)
    
    with pytest.raises(ValidationError):
        TrailingStopConfig(activation_profit_pct=0.1, trail_pct=0)
