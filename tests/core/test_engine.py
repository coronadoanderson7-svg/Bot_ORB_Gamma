import pytest
from unittest.mock import MagicMock, patch

from core.engine import Engine

@pytest.fixture
def mock_dependencies(mocker):
    """Mocks all external dependencies for the Engine."""
    mocker.patch('core.engine.IBConnector', MagicMock())
    mocker.patch('core.engine.OpeningRangeStrategy', MagicMock())
    mocker.patch('core.engine.BreakoutStrategy', MagicMock())
    mocker.patch('core.engine.GEXAnalyzer', MagicMock())
    mocker.patch('core.engine.OrderManager', MagicMock())
    # Also mock the config loader at the engine level
    mocker.patch('core.engine.APP_CONFIG', MagicMock())

def test_engine_initialization(mock_dependencies):
    """
    Tests that the Engine initializes correctly and sets the initial state.
    """
    # Act
    engine = Engine()

    # Assert
    assert engine.state == "INITIALIZING"
    assert engine.ib_connector is not None
    assert engine.orb_strategy is not None
    assert engine.breakout_strategy is not None
    assert engine.gex_analyzer is not None
    assert engine.order_manager is not None

def test_run_state_transitions(mock_dependencies, mocker):
    """
    Tests the basic state transition logic of the run method.
    This is a simplified test to ensure the state machine advances.
    """
    # Arrange
    engine = Engine()
    
    # Mock the state processing methods to control the state flow
    mocker.patch.object(engine, '_process_state', side_effect=lambda: setattr(engine, 'state', 'SHUTDOWN'))

    # Act
    engine.run()

    # Assert
    # Check that _process_state was called, driving the state machine forward
    engine._process_state.assert_called()
    # The side effect will immediately shut it down, so we just care that it ran.
    assert engine.state == "SHUTDOWN"
