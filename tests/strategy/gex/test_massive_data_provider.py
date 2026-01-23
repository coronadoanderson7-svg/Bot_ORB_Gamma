# tests/strategy/gex/test_massive_data_provider.py

import unittest
from unittest.mock import patch, MagicMock
import requests

from core.config_loader import Config
from strategy.gex.massive_data_provider import MassiveDataProvider

class TestMassiveDataProvider(unittest.TestCase):

    def setUp(self):
        """Set up a mock config and MassiveDataProvider instance for testing."""
        self.mock_config = Config.parse_obj({
            "gex": {
                "days_to_expiration": 0,
                "strikes_quantity": 120,
                "option_multiplier": 100,
                "providers": {
                    "massive_data": {
                        "base_url": "https://fakeapi.massive.com/v1",
                        "api_key": "fake_api_key"
                    }
                }
            }
        })
        self.provider = MassiveDataProvider(self.mock_config)

    @patch('requests.Session.get')
    def test_get_max_gamma_strike_success(self, mock_get):
        """Test successful retrieval and calculation of the max gamma strike."""
        # Arrange: Mock a successful API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "expiration": "2026-01-21",
            "options": [
                # Strike 5000: GEX = (0.0015 * 1520 * 100) + (0.0014 * 2100 * 100) = 228000 + 294000 = 522000
                {"strike": 5000.0, "type": "call", "openInterest": 1520, "greeks": {"gamma": 0.0015}},
                {"strike": 5000.0, "type": "put", "openInterest": 2100, "greeks": {"gamma": 0.0014}},
                # Strike 5010: GEX = (0.0020 * 1000 * 100) = 200000
                {"strike": 5010.0, "type": "call", "openInterest": 1000, "greeks": {"gamma": 0.0020}},
            ]
        }
        mock_get.return_value = mock_response

        # Act
        max_strike, exp_date = self.provider.get_max_gamma_strike("SPX")

        # Assert
        self.assertEqual(max_strike, 5000.0)
        self.assertEqual(exp_date, "20260121")

        # Verify the request was made correctly
        expected_url = "https://fakeapi.massive.com/v1/options/chain"
        expected_headers = {"Authorization": "Bearer fake_api_key"}
        expected_params = {
            "ticker": "SPX",
            "days_to_expiration": 0,
            "strikes_quantity": 120,
            "fields": "greeks,openInterest"
        }
        mock_get.assert_called_once_with(expected_url, params=expected_params, headers=expected_headers, timeout=10)

    @patch('requests.Session.get')
    def test_get_max_gamma_strike_api_error(self, mock_get):
        """Test the case where the API request fails."""
        # Arrange: Mock a request exception
        mock_get.side_effect = requests.exceptions.RequestException("API is down")

        # Act
        max_strike, exp_date = self.provider.get_max_gamma_strike("SPX")

        # Assert
        self.assertEqual(max_strike, 0.0)
        self.assertEqual(exp_date, "")

    @patch('requests.Session.get')
    def test_get_max_gamma_strike_no_data(self, mock_get):
        """Test the case where the API returns an empty options list."""
        # Arrange: Mock an empty data response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "expiration": "2026-01-21",
            "options": []
        }
        mock_get.return_value = mock_response

        # Act
        max_strike, exp_date = self.provider.get_max_gamma_strike("SPX")

        # Assert
        self.assertEqual(max_strike, 0.0)
        self.assertEqual(exp_date, "")
        
    @patch('requests.Session.get')
    def test_get_max_gamma_strike_validation_error(self, mock_get):
        """Test the case where the API returns a malformed response."""
        # Arrange: Mock a malformed response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"invalid_key": "some_value"} # Missing 'expiration' and 'options'
        mock_get.return_value = mock_response

        # Act
        max_strike, exp_date = self.provider.get_max_gamma_strike("SPX")

        # Assert
        self.assertEqual(max_strike, 0.0)
        self.assertEqual(exp_date, "")

if __name__ == '__main__':
    unittest.main()