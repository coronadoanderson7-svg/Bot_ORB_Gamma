import logging
from datetime import datetime, timedelta
from typing import Protocol, Dict, Any, Literal, List, Optional

# Define a Protocol for bar-like objects for type safety
class BarLike(Protocol):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int

# Define the possible signal outcomes
Signal = Literal["BULLISH", "BEARISH", "NO SIGNAL"]

class BreakoutStrategy:
    """
    Stage 2: Breakout Detection.

    This strategy is stateful. It aggregates 5-second real-time bars into larger
    candles (e.g., 5-minute) and then checks for breakouts from the opening range.
    """

    def __init__(self, aggregation_seconds: int):
        """
        Initialize the Breakout Strategy.

        Args:
            aggregation_seconds (int): The duration in seconds to aggregate
                                       5-second bars into a single candle
                                       (e.g., 300 for a 5-minute candle).
        """
        if aggregation_seconds % 5 != 0:
            raise ValueError("Aggregation seconds must be a multiple of 5.")
            
        self.aggregation_seconds = aggregation_seconds
        self.bars_to_aggregate = aggregation_seconds // 5
        
        self.five_second_bars: List[BarLike] = []
        self.logger = logging.getLogger(__name__)
        self.logger.info(
            f"Breakout strategy initialized to aggregate "
            f"{self.bars_to_aggregate} 5-sec bars into {aggregation_seconds}-sec candles."
        )

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "BreakoutStrategy":
        """
        Factory method to initialize the strategy from the application configuration.
        """
        breakout_cfg = config.get("breakout", {})
        agg_seconds = breakout_cfg.get("bar_size_seconds", 300)
        return cls(aggregation_seconds=agg_seconds)

    def add_realtime_bar(self, bar: BarLike, high_level: float, low_level: float) -> Signal:
        """
        Adds a new 5-second real-time bar and checks for a breakout if a full
        candle has been aggregated.

        Args:
            bar (BarLike): The incoming 5-second real-time bar.
            high_level (float): The high level of the opening range.
            low_level (float): The low level of the opening range.

        Returns:
            Signal: The breakout signal if a candle was completed, otherwise "NO SIGNAL".
        """
        # Align timestamps to the start of the aggregation window (e.g., 5-min interval)
        if self.five_second_bars:
            first_bar_ts = self.five_second_bars[0].timestamp
            window_start_ts = first_bar_ts - timedelta(microseconds=first_bar_ts.microsecond, seconds=first_bar_ts.second % self.aggregation_seconds)
            window_end_ts = window_start_ts + timedelta(seconds=self.aggregation_seconds)
            
            # If a bar arrives outside the current window, something is wrong. Reset.
            if not window_start_ts <= bar.timestamp < window_end_ts:
                self.logger.warning(
                    f"Bar {bar.timestamp} arrived outside of current aggregation window "
                    f"({window_start_ts} - {window_end_ts}). Resetting aggregator."
                )
                self.five_second_bars = []

        self.five_second_bars.append(bar)
        self.logger.debug(f"Aggregator: Added 5s bar. Count: {len(self.five_second_bars)}/{self.bars_to_aggregate}")

        if len(self.five_second_bars) == self.bars_to_aggregate:
            self.logger.info(f"Aggregator: Completed a {self.aggregation_seconds}s candle. Checking for breakout.")
            
            # Aggregate the bars into one candle
            aggregated_candle = self._aggregate_bars()
            
            # Reset for the next interval BEFORE checking breakout
            self.five_second_bars = []
            
            # Check for breakout using the newly formed candle
            return self.check_breakout(aggregated_candle, high_level, low_level)
            
        return "NO SIGNAL"

    def _aggregate_bars(self) -> Optional[BarLike]:
        """
        Creates a single candle from the list of collected 5-second bars.
        """
        if not self.five_second_bars:
            return None

        # Create a new Bar object for the aggregated candle
        # We can use a simple class or dict that matches the BarLike protocol
        class AggregatedBar:
            timestamp: datetime
            open: float
            high: float
            low: float
            close: float
            volume: int

        agg_bar = AggregatedBar()
        agg_bar.timestamp = self.five_second_bars[0].timestamp
        agg_bar.open = self.five_second_bars[0].open
        agg_bar.high = max(b.high for b in self.five_second_bars)
        agg_bar.low = min(b.low for b in self.five_second_bars)
        agg_bar.close = self.five_second_bars[-1].close
        agg_bar.volume = sum(b.volume for b in self.five_second_bars)
        
        self.logger.debug(
            f"Aggregated Candle: T:{agg_bar.timestamp} "
            f"O:{agg_bar.open} H:{agg_bar.high} L:{agg_bar.low} C:{agg_bar.close}"
        )
        return agg_bar

    def check_breakout(self, bar: BarLike, high_level: float, low_level: float) -> Signal:
        """
        Checks for a breakout condition based on an aggregated candle.
        This logic remains the same as before.
        """
        if not all([bar, high_level is not None, low_level is not None]):
            self.logger.warning("Check breakout called with invalid inputs.")
            return "NO SIGNAL"

        c_open, c_close, c_high, c_low = bar.open, bar.close, bar.high, bar.low
        
        self.logger.debug(
            f"Checking breakout for candle {bar.timestamp} | "
            f"O:{c_open} H:{c_high} L:{c_low} C:{c_close} | "
            f"Range: {high_level:.2f} - {low_level:.2f}"
        )

        # High Breakout (Bullish Signal)
        if (c_close > c_open) and (c_low > high_level):
            self.logger.info(f"BULLISH breakout detected at {bar.timestamp} (Close: {c_close}) above High Level ({high_level:.2f})")
            return "BULLISH"

        # Low Breakout (Bearish Signal)
        if (c_close < c_open) and (c_high < low_level):
            self.logger.info(f"BEARISH breakout detected at {bar.timestamp} (Close: {c_close}) below Low Level ({low_level:.2f})")
            return "BEARISH"
            
        return "NO SIGNAL"

if __name__ == '__main__':
    # Example Usage for testing purposes
    
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

    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # --- Test Case: Bullish Breakout ---
    print("\n--- Testing Bullish Breakout Aggregation ---")
    config_data = {"breakout": {"bar_size_seconds": 60}} # Aggregate into 1-min candles for testing
    strategy = BreakoutStrategy.from_config(config_data)
    
    orb_high = 4000.0
    orb_low = 3990.0
    start_time = datetime.now().replace(second=0, microsecond=0)
    
    # Simulate 12 5-second bars that form a bullish breakout candle
    signal = "NO SIGNAL"
    for i in range(12):
        ts = start_time + timedelta(seconds=i*5)
        # Candle starts at 4001, moves up to 4005, body stays above 4000
        bar = MockBar(ts, 4001 + i*0.2, 4001.5 + i*0.2, 4000.5 + i*0.2, 4001.2 + i*0.2)
        signal = strategy.add_realtime_bar(bar, orb_high, orb_low)
        print(f"Added bar {i+1}/12. Signal: {signal}")

    print(f"Final Signal: Expected BULLISH, Got: {signal}")
    assert signal == "BULLISH"
    
    # --- Test Case: Bearish Breakout ---
    print("\n--- Testing Bearish Breakout Aggregation ---")
    strategy = BreakoutStrategy.from_config(config_data) # Reset strategy
    signal = "NO SIGNAL"
    
    # Simulate 12 5-second bars that form a bearish breakout candle
    for i in range(12):
        ts = start_time + timedelta(seconds=i*5)
        # Candle starts at 3989, moves down to 3985, body stays below 3990
        bar = MockBar(ts, 3989 - i*0.2, 3989.5 - i*0.2, 3988.5 - i*0.2, 3988.8 - i*0.2)
        signal = strategy.add_realtime_bar(bar, orb_high, orb_low)
        print(f"Added bar {i+1}/12. Signal: {signal}")

    print(f"Final Signal: Expected BEARISH, Got: {signal}")
    assert signal == "BEARISH"

    # --- Test Case: No Breakout ---
    print("\n--- Testing No Breakout (Inside Range) ---")
    strategy = BreakoutStrategy.from_config(config_data) # Reset strategy
    signal = "NO SIGNAL"
    for i in range(12):
        ts = start_time + timedelta(seconds=i*5)
        bar = MockBar(ts, 3995, 3996, 3994, 3995.5)
        signal = strategy.add_realtime_bar(bar, orb_high, orb_low)
    
    print(f"Final Signal: Expected NO SIGNAL, Got: {signal}")
    assert signal == "NO SIGNAL"
    
    print("\n--- All tests passed! ---")
