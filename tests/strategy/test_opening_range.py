import pytest
from datetime import datetime
from strategy.opening_range import OpeningRangeStrategy
from models.data_models import Bar

@pytest.fixture
def orb_strategy():
    """Fixture to create an OpeningRangeStrategy instance."""
    config = {"opening_range": {"duration_minutes": 30}}
    return OpeningRangeStrategy.from_config(config)

@pytest.fixture
def sample_bars():
    """Fixture to create a list of sample bars."""
    base_time = datetime.now()
    bars = [
        Bar(timestamp=base_time, open=100, high=105, low=99, close=102, volume=1000),
        Bar(timestamp=base_time, open=102, high=110, low=101, close=108, volume=1000),
        Bar(timestamp=base_time, open=108, high=109, low=98, close=105, volume=1000),
    ]
    return bars

def test_calculate_levels(orb_strategy: OpeningRangeStrategy, sample_bars):
    """
    Tests that the calculate_levels method correctly identifies the high and low
    from a series of bars.
    """
    # Arrange
    for bar in sample_bars:
        orb_strategy.add_bar(bar)
    
    # Act
    high, low = orb_strategy.calculate_levels()

    # Assert
    assert high == 110 # The highest high from the sample bars
    assert low == 98   # The lowest low from the sample bars

def test_calculate_levels_no_bars(orb_strategy: OpeningRangeStrategy):
    """
    Tests that calculate_levels returns (None, None) when no bars have been added.
    """
    # Act
    high, low = orb_strategy.calculate_levels()

    # Assert
    assert high is None
    assert low is None
