import pytest
from unittest.mock import MagicMock, patch
from datetime import date, timedelta

from strategy.gex_analyzer import GEXAnalyzer
from ibapi.contract import Contract, ContractDetails

@pytest.fixture
def mock_config():
    return {
        "gex": {"days_to_expiration": 0, "strikes_quantity": 10, "option_multiplier": 100},
        "instrument": {"ticker": "SPX", "exchange": "CBOE", "currency": "USD"},
    }

@patch('strategy.gex_analyzer.GEXAnalyzer._get_underlying_spot_price', return_value=450.0)
@patch('strategy.gex_analyzer.GEXAnalyzer._get_option_parameters')
@patch('strategy.gex_analyzer.GEXAnalyzer._calculate_gex_for_strikes')
def test_find_and_calculate_gex_orchestration(
    mock_calc_gex, mock_get_params, mock_get_price, mock_config
):
    """
    Tests the main orchestration of the find_and_calculate_gex method,
    mocking out the complex helper methods.
    """
    # Arrange
    mock_connector = MagicMock()
    
    mock_details = ContractDetails()
    mock_details.contract = Contract()
    mock_details.contract.conId = 12345
    mock_details.marketName = "CBOE"
    mock_connector.resolve_contract_details.return_value = mock_details
    
    expirations = [(date.today() + timedelta(days=i)).strftime("%Y%m%d") for i in range(5)]
    strikes = [float(i) for i in range(400, 500, 5)]
    mock_get_params.return_value = (expirations, strikes)
    
    mock_calc_gex.return_value = {450: 1000, 455: 2000, 460: 500}

    analyzer = GEXAnalyzer(connector=mock_connector, config=mock_config)

    # Act
    result = analyzer.find_and_calculate_gex()

    # Assert
    assert result is not None
    highest_gex_strike, target_expiration = result
    
    mock_connector.resolve_contract_details.assert_called_once()
    mock_get_params.assert_called_once()
    mock_get_price.assert_called_once()
    mock_calc_gex.assert_called_once()
    
    assert target_expiration == date.today().strftime("%Y%m%d")
    assert highest_gex_strike == 455 # The one with the highest GEX from the mock
