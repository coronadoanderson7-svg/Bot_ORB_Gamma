import logging
from datetime import datetime, timedelta
from typing import Protocol, Dict, Any, List, Optional

from models.data_models import Bar, Signal, SignalType

class BreakoutStrategy:
    """
    Stage 2: Breakout Detection.

    This strategy is stateful. It aggregates 5-second real-time bars into larger
    candles (e.g., 5-minute) and then checks for breakouts from the opening range.
    It ensures that aggregated candles are aligned to standard clock intervals.
    """

    def __init__(self, aggregation_seconds: int, symbol: str):
        """
        Initialize the Breakout Strategy.

        Args:
            aggregation_seconds (int): The duration in seconds to aggregate
                                       5-second bars into a single candle
                                       (e.g., 300 for a 5-minute candle).
            symbol (str): The symbol of the instrument being traded.
        """
        if aggregation_seconds <= 0:
            raise ValueError("Aggregation seconds must be a positive integer.")
            
        self.aggregation_seconds = aggregation_seconds
        self.symbol = symbol
        
        self.in_progress_bar: Optional[Bar] = None
        self.logger = logging.getLogger(__name__)
        self.logger.info(
            f"Breakout strategy initialized for {self.symbol} to aggregate "
            f"5-sec bars into {aggregation_seconds}-sec candles."
        )

    @classmethod
    def from_config(cls, config: Dict[str, Any], symbol: str) -> "BreakoutStrategy":
        """
        Factory method to initialize the strategy from the application configuration.
        """
        breakout_cfg = config.get("breakout", {})
        agg_seconds = breakout_cfg.get("bar_size_seconds", 300)
        return cls(aggregation_seconds=agg_seconds, symbol=symbol)

    def add_realtime_bar(self, bar: Bar, high_level: float, low_level: float) -> Signal:
        """
        Adds a new 5-second real-time bar, aggregates it into a larger candle,
        and checks for a breakout when a candle is completed.

        Args:
            bar (Bar): The incoming 5-second real-time bar.
            high_level (float): The high level of the opening range.
            low_level (float): The low level of the opening range.

        Returns:
            Signal: The breakout signal if a candle was completed, otherwise a "HOLD" signal.
        """
        # Truncate the timestamp to the floor of the aggregation window
        bar_timestamp_unix = bar.timestamp.timestamp()
        truncated_timestamp_unix = (bar_timestamp_unix // self.aggregation_seconds) * self.aggregation_seconds
        truncated_timestamp = datetime.fromtimestamp(truncated_timestamp_unix)

        completed_bar = None

        # If there's no bar in progress, start a new one
        if self.in_progress_bar is None:
            self.logger.info(f"Starting new aggregated candle at {truncated_timestamp}")
            self.in_progress_bar = Bar(
                timestamp=truncated_timestamp,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume
            )
        # If the new bar belongs to the same time window, update the in-progress bar
        elif self.in_progress_bar.timestamp == truncated_timestamp:
            self.in_progress_bar.high = max(self.in_progress_bar.high, bar.high)
            self.in_progress_bar.low = min(self.in_progress_bar.low, bar.low)
            self.in_progress_bar.close = bar.close
            self.in_progress_bar.volume += bar.volume
            self.logger.debug(f"Updating candle {self.in_progress_bar.timestamp}: C:{self.in_progress_bar.close} H:{self.in_progress_bar.high} L:{self.in_progress_bar.low}")
        # If the bar starts a new window, the old one is complete
        else:
            self.logger.info(f"Completed candle for {self.in_progress_bar.timestamp}. Checking for breakout.")
            completed_bar = self.in_progress_bar
            
            # Start the next bar
            self.logger.info(f"Starting new aggregated candle at {truncated_timestamp}")
            self.in_progress_bar = Bar(
                timestamp=truncated_timestamp,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume
            )
            
        # If a bar was completed in this step, check for a breakout
        if completed_bar:
            return self.check_breakout(completed_bar, high_level, low_level)
            
        return Signal(timestamp=bar.timestamp, symbol=self.symbol, signal_type=SignalType.HOLD, strategy="BreakoutStrategy")

    def check_breakout(self, bar: Bar, high_level: float, low_level: float) -> Signal:
        """
        Checks for a breakout condition based on an aggregated candle.
        """
        if not all([bar, high_level is not None, low_level is not None]):
            self.logger.warning("Check breakout called with invalid inputs.")
            return Signal(timestamp=datetime.now(), symbol=self.symbol, signal_type=SignalType.HOLD, strategy="BreakoutStrategy")

        c_open, c_close, c_high, c_low = bar.open, bar.close, bar.high, bar.low
        
        self.logger.debug(
            f"Checking breakout for candle {bar.timestamp} | "
            f"O:{c_open} H:{c_high} L:{c_low} C:{c_close} | "
            f"Range: {high_level:.2f} - {low_level:.2f}"
        )

        # High Breakout (Bullish Signal)
        if (c_close > c_open) and (c_low > high_level):
            self.logger.info(f"BULLISH breakout detected at {bar.timestamp} (Close: {c_close}) above High Level ({high_level:.2f})")
            return Signal(timestamp=bar.timestamp, symbol=self.symbol, signal_type=SignalType.BUY, strategy="BreakoutStrategy", price=bar.close)

        # Low Breakout (Bearish Signal)
        if (c_close < c_open) and (c_high < low_level):
            self.logger.info(f"BEARISH breakout detected at {bar.timestamp} (Close: {c_close}) below Low Level ({low_level:.2f})")
            return Signal(timestamp=bar.timestamp, symbol=self.symbol, signal_type=SignalType.SELL, strategy="BreakoutStrategy", price=bar.close)
            
        return Signal(timestamp=bar.timestamp, symbol=self.symbol, signal_type=SignalType.HOLD, strategy="BreakoutStrategy")
