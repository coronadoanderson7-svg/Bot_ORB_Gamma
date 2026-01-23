import pytest
from datetime import datetime, timedelta
from strategy.breakout import BreakoutStrategy
from models.data_models import Bar, Signal, SignalType

@pytest.fixture
def breakout_strategy():
    """Fixture to create a BreakoutStrategy instance for testing."""
    # Aggregate into 1-min candles for simpler testing (12 * 5s bars)
    config_data = {"breakout": {"bar_size_seconds": 60}} 
    return BreakoutStrategy.from_config(config_data, symbol="TEST")

def test_bullish_breakout(breakout_strategy: BreakoutStrategy):
    """
    Tests that a bullish breakout signal is correctly generated when a candle
    forms completely above the opening range high.
    """
    orb_high = 4000.0
    orb_low = 3990.0
    start_time = datetime.now().replace(second=0, microsecond=0)
    
    # Simulate 12 5-second bars that form a bullish breakout candle
    for i in range(12):
        ts = start_time + timedelta(seconds=i*5)
        # Candle starts at 4001, moves up, and its low stays above the ORB high
        bar = Bar(timestamp=ts, open=4001 + i*0.2, high=4001.5 + i*0.2, low=4000.5 + i*0.2, close=4001.2 + i*0.2, volume=10)
        signal = breakout_strategy.add_realtime_bar(bar, orb_high, orb_low)
        # No signal should be generated until the candle is complete
        assert signal.signal_type == SignalType.HOLD

    # The 13th bar arrives, completing the previous candle and triggering the check
    final_bar_ts = start_time + timedelta(seconds=12*5)
    final_bar = Bar(timestamp=final_bar_ts, open=4003, high=4004, low=4003, close=4003.5, volume=10)
    signal = breakout_strategy.add_realtime_bar(final_bar, orb_high, orb_low)

    assert signal.signal_type == SignalType.BUY
    assert signal.price == 4001.2 + (11 * 0.2) # Close of the last bar of the aggregated candle

def test_bearish_breakout(breakout_strategy: BreakoutStrategy):
    """
    Tests that a bearish breakout signal is correctly generated when a candle
    forms completely below the opening range low.
    """
    orb_high = 4000.0
    orb_low = 3990.0
    start_time = datetime.now().replace(second=0, microsecond=0)
    
    # Simulate 12 5-second bars that form a bearish breakout candle
    for i in range(12):
        ts = start_time + timedelta(seconds=i*5)
        # Candle starts at 3989, moves down, and its high stays below the ORB low
        bar = Bar(timestamp=ts, open=3989 - i*0.2, high=3989.5 - i*0.2, low=3988.5 - i*0.2, close=3988.8 - i*0.2, volume=10)
        signal = breakout_strategy.add_realtime_bar(bar, orb_high, orb_low)
        assert signal.signal_type == SignalType.HOLD
    
    # The 13th bar arrives, completing the previous candle
    final_bar_ts = start_time + timedelta(seconds=12*5)
    final_bar = Bar(timestamp=final_bar_ts, open=3985, high=3986, low=3985, close=3985.5, volume=10)
    signal = breakout_strategy.add_realtime_bar(final_bar, orb_high, orb_low)

    assert signal.signal_type == SignalType.SELL

def test_no_breakout_inside_range(breakout_strategy: BreakoutStrategy):
    """
    Tests that no breakout signal is generated when the candle forms entirely
    inside the opening range.
    """
    orb_high = 4000.0
    orb_low = 3990.0
    start_time = datetime.now().replace(second=0, microsecond=0)
    
    # Simulate 12 5-second bars that form a candle inside the range
    for i in range(12):
        ts = start_time + timedelta(seconds=i*5)
        bar = Bar(timestamp=ts, open=3995, high=3996, low=3994, close=3995.5, volume=10)
        signal = breakout_strategy.add_realtime_bar(bar, orb_high, orb_low)
        assert signal.signal_type == SignalType.HOLD
    
    # The 13th bar arrives, completing the previous candle
    final_bar_ts = start_time + timedelta(seconds=12*5)
    final_bar = Bar(timestamp=final_bar_ts, open=3995, high=3996, low=3994, close=3995.5, volume=10)
    signal = breakout_strategy.add_realtime_bar(final_bar, orb_high, orb_low)

    # The completed candle was inside the range, so the signal should still be HOLD
    assert signal.signal_type == SignalType.HOLD

def test_aggregation_with_misaligned_timestamps(breakout_strategy: BreakoutStrategy):
    """
    Tests that the bar aggregator correctly buckets bars into standard clock
    intervals, even if the first bar's timestamp is not perfectly aligned.
    """
    orb_high = 4000.0
    orb_low = 3990.0
    # Start with a misaligned time, e.g., 7 seconds into the minute
    misaligned_start_time = datetime.now().replace(second=7, microsecond=0)

    # These bars should all be bucketed into the candle starting at second 0
    for i in range(11): # From 00:07 to 00:57 (11 bars)
        ts = misaligned_start_time + timedelta(seconds=i * 5)
        bar = Bar(timestamp=ts, open=4001, high=4002, low=4000.5, close=4001.5, volume=10)
        signal = breakout_strategy.add_realtime_bar(bar, orb_high, orb_low)
        assert signal.signal_type == SignalType.HOLD
    
    # This bar arrives at 01:02, which is in the *next* time bucket.
    # This should complete the previous candle and trigger the breakout check.
    final_bar_ts = misaligned_start_time + timedelta(seconds=11*5)
    final_bar = Bar(timestamp=final_bar_ts, open=4003, high=4004, low=4003, close=4003.5, volume=10)
    signal = breakout_strategy.add_realtime_bar(final_bar, orb_high, orb_low)

    # The completed candle (from 00:07 to 00:57) met the bullish criteria
    assert signal.signal_type == SignalType.BUY
    assert breakout_strategy.in_progress_bar is not None
    # Check that the new in-progress bar has been correctly truncated to the minute
    assert breakout_strategy.in_progress_bar.timestamp.second == 0
    assert breakout_strategy.in_progress_bar.timestamp.minute == (final_bar_ts.minute)
