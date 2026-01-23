# tests/strategy/gex/test_gexbot_provider.py

import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
import requests

from core.config_loader import Config
from strategy.gex.gexbot_provider import GexbotProvider

class TestGexbotProvider(unittest.TestCase):

    def setUp(self):
        """Set up a mock config and GexbotProvider instance for testing."""
        self.mock_config = Config.parse_obj({
            "gex": {
                "days_to_expiration": 0,
                "providers": {
                    "gexbot": {
                        "base_url": "https://fakeapi.gexbot.com",
                        "api_key": "fake_api_key"
                    }
                }
            }
        })
        self.provider = GexbotProvider(self.mock_config)

    @patch('requests.Session.get')
    def test_get_max_gamma_strike_success(self, mock_get):
        """Test successful retrieval and calculation of the max gamma strike."""
        # Arrange: Mock a successful API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "success": True,
            "data": [
                {"strike": 5000, "long_gamma": 1000, "short_gamma": -500},  # Total GEX = 1500
                {"strike": 5010, "long_gamma": 2000, "short_gamma": -1500}, # Total GEX = 3500 (Max)
                {"strike": 5020, "long_gamma": 500, "short_gamma": -200},   # Total GEX = 700
            ]
        }
        mock_get.return_value = mock_response

        # Act
        max_strike, exp_date = self.provider.get_max_gamma_strike("SPX")

        # Assert
        self.assertEqual(max_strike, 5010)
        expected_date = (datetime.now() + timedelta(days=0)).strftime('%Y%m%d')
        self.assertEqual(exp_date, expected_date)

        # Verify the request was made correctly
        expected_url = "https://fakeapi.gexbot.com/gex/distribution"
        expected_params = {
            "ticker": "SPX",
            "exp": (datetime.now() + timedelta(days=0)).strftime('%Y-%m-%d'),
            "api_key": "fake_api_key"
        }
        mock_get.assert_called_once_with(expected_url, params=expected_params, headers=None, timeout=10)

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
        """Test the case where the API returns success but no data."""
        # Arrange: Mock an empty data response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "success": True,
            "data": []
        }
        mock_get.return_value = mock_response

        # Act
        max_strike, exp_date = self.provider.get_max_gamma_strike("SPX")

        # Assert
        self.assertEqual(max_strike, 0.0)
        self.assertEqual(exp_date, "")

    @patch('requests.Session.get')
    def test_get_max_gamma_strike_api_success_false(self, mock_get):
        """Test the case where the API returns success: false."""
        # Arrange: Mock a "success: false" response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "success": False,
            "data": []
        }
        mock_get.return_value = mock_response

        # Act
        max_strike, exp_date = self.provider.get_max_gamma_strike("SPX")

        # Assert
        self.assertEqual(max_strike, 0.0)
        self.assertEqual(exp_date, "")

if __name__ == '__main__':
    unittest.main()