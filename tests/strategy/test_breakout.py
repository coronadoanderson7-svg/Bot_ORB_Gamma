import pytest
from datetime import datetime, timedelta
from strategy.breakout import BreakoutStrategy, BarLike
from models.data_models import Signal, SignalType

class MockBar:
    def __init__(self, timestamp, o, h, l, c, v=10):
        self.timestamp = timestamp
        self.open = o
        self.high = h
        self.low = l
        self.close = c
        self.volume = v
    def __repr__(self):
        return f"Bar(T={self.timestamp.time()}, O={self.open}, H={self.high}, L={self.low}, C={self.close})"

@pytest.fixture
def breakout_strategy():
    """Fixture to create a BreakoutStrategy instance for testing."""
    config_data = {"breakout": {"bar_size_seconds": 60}} # Aggregate into 1-min candles
    return BreakoutStrategy.from_config(config_data, symbol="TEST")

def test_bullish_breakout(breakout_strategy: BreakoutStrategy):
    """
    Tests that a bullish breakout signal is correctly generated when a candle
    forms completely above the opening range high.
    """
    orb_high = 4000.0
    orb_low = 3990.0
    start_time = datetime.now().replace(second=0, microsecond=0)
    
    signal = Signal(timestamp=datetime.now(), symbol="TEST", signal_type=SignalType.HOLD, strategy="BreakoutStrategy")
    
    # Simulate 12 5-second bars that form a bullish breakout candle
    for i in range(12):
        ts = start_time + timedelta(seconds=i*5)
        # Candle starts at 4001, moves up, and its low stays above the ORB high
        bar = MockBar(ts, 4001 + i*0.2, 4001.5 + i*0.2, 4000.5 + i*0.2, 4001.2 + i*0.2)
        signal = breakout_strategy.add_realtime_bar(bar, orb_high, orb_low)

    assert signal.signal_type == SignalType.BUY

def test_bearish_breakout(breakout_strategy: BreakoutStrategy):
    """
    Tests that a bearish breakout signal is correctly generated when a candle
    forms completely below the opening range low.
    """
    orb_high = 4000.0
    orb_low = 3990.0
    start_time = datetime.now().replace(second=0, microsecond=0)
    
    signal = Signal(timestamp=datetime.now(), symbol="TEST", signal_type=SignalType.HOLD, strategy="BreakoutStrategy")
    
    # Simulate 12 5-second bars that form a bearish breakout candle
    for i in range(12):
        ts = start_time + timedelta(seconds=i*5)
        # Candle starts at 3989, moves down, and its high stays below the ORB low
        bar = MockBar(ts, 3989 - i*0.2, 3989.5 - i*0.2, 3988.5 - i*0.2, 3988.8 - i*0.2)
        signal = breakout_strategy.add_realtime_bar(bar, orb_high, orb_low)

    assert signal.signal_type == SignalType.SELL

def test_no_breakout_inside_range(breakout_strategy: BreakoutStrategy):
    """
    Tests that no breakout signal is generated when the candle forms entirely
    inside the opening range.
    """
    orb_high = 4000.0
    orb_low = 3990.0
    start_time = datetime.now().replace(second=0, microsecond=0)
    
    signal = Signal(timestamp=datetime.now(), symbol="TEST", signal_type=SignalType.HOLD, strategy="BreakoutStrategy")
    
    # Simulate 12 5-second bars that form a candle inside the range
    for i in range(12):
        ts = start_time + timedelta(seconds=i*5)
        bar = MockBar(ts, 3995, 3996, 3994, 3995.5)
        signal = breakout_strategy.add_realtime_bar(bar, orb_high, orb_low)
    
    assert signal.signal_type == SignalType.HOLD
