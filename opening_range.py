import logging
from datetime import datetime, time, timedelta
from typing import List, Optional, Tuple, Protocol, Dict, Any

# Define a Protocol to ensure type safety for the Bar object
# This allows the strategy to work with any Bar object (Pydantic, Dataclass, etc.)
# that has these attributes, without strictly importing from models.data_models yet.
class BarLike(Protocol):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int

class OpeningRangeStrategy:
    """
    Stage 1: Opening Range Identification.
    
    The goal is to define the initial price range during the first 30 minutes 
    of the market session.
    """

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "OpeningRangeStrategy":
        """
        Factory method to initialize the strategy from the application configuration.
        
        Args:
            config (dict): The full application configuration dictionary.
                           Expects an 'opening_range' section.
        """
        orb_cfg = config.get("opening_range", {})
        
        # Parse market_open_time from string "HH:MM:SS"
        mo_str = orb_cfg.get("market_open_time", "09:30:00")
        market_open = datetime.strptime(mo_str, "%H:%M:%S").time()
        
        duration = orb_cfg.get("duration_minutes", 30)
        return cls(market_open=market_open, duration_minutes=duration)

    def __init__(self, market_open: time = time(9, 30), duration_minutes: int = 30):
        """
        Initialize the Opening Range Strategy.

        Args:
            market_open (time): The market start time (default 09:30 EST).
            duration_minutes (int): The duration of the opening range (default 30 mins).
        """
        self.market_open = market_open
        self.duration_minutes = duration_minutes
        
        # State
        self.bars: List[BarLike] = []
        self.high_level: Optional[float] = None
        self.low_level: Optional[float] = None
        self.is_complete: bool = False
        
        self.logger = logging.getLogger(__name__)

    def add_bar(self, bar: BarLike) -> bool:
        """
        Adds a bar to the collection if it falls within the opening range window.
        
        Note: Assumes bars are of the correct resolution (e.g., 1 min) as per config.
        Returns:
            bool: True if the bar was added, False if it was ignored (outside window).
        """
        if self.is_bar_valid(bar):
            self.bars.append(bar)
            self.logger.debug(f"ORB: Bar added {bar.timestamp} | H: {bar.high} L: {bar.low}")
            return True
        
        self.logger.debug(f"ORB: Bar ignored (outside window) {bar.timestamp}")
        return False

    def is_bar_valid(self, bar: BarLike) -> bool:
        """
        Checks if the bar is strictly within the market open window.
        """
        bar_dt = bar.timestamp
        # Construct the specific open/close datetimes for the date of this bar
        session_open = datetime.combine(bar_dt.date(), self.market_open)
        session_end = session_open + timedelta(minutes=self.duration_minutes)

        # Check if bar is within [start, end)
        # Example: 09:30:00 is valid. 09:59:00 is valid. 10:00:00 is NOT valid.
        return session_open <= bar_dt < session_end

    def calculate_levels(self) -> Tuple[Optional[float], Optional[float]]:
        """
        Calculates the HIGH_LEVEL and LOW_LEVEL from the collected bars.
        
        Returns:
            Tuple[float, float]: (HIGH_LEVEL, LOW_LEVEL)
        """
        if not self.bars:
            self.logger.warning("ORB: No bars collected. Cannot calculate levels.")
            return None, None

        self.high_level = max(b.high for b in self.bars)
        self.low_level = min(b.low for b in self.bars)
        self.is_complete = True

        self.logger.info(f"ORB: Range Calculated | High: {self.high_level} | Low: {self.low_level}")
        return self.high_level, self.low_level