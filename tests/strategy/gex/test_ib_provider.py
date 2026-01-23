# tests/strategy/gex/test_ib_provider.py
import unittest
from unittest.mock import MagicMock, patch, call
from queue import Empty, Queue
from datetime import datetime, timedelta

from ibapi.contract import Contract, ContractDetails

from core.config_loader import AppConfig
from strategy.gex.factory import get_gex_provider
from strategy.gex.ib_provider import IBProvider
from strategy.gex.base_provider import BaseGexProvider

class TestIBProvider(unittest.TestCase):
    """
    Test suite for the IBProvider and its integration.
    """

    def setUp(self):
        """Set up mock config and connector for each test."""
        self.full_mock_config = {
            "connection": {"host": "127.0.0.1", "port": 7496, "client_id": 1},
            "account": {"type": "paper", "code": "DU12345"},
            "instrument": {"ticker": "SPX", "exchange": "CBOE", "currency": "USD", "exchange_timezone": "America/New_York"},
            "opening_range": {"market_open_time": "09:30", "duration_minutes": 1, "bar_size": "5 secs", "wait_buffer_seconds": 5, "historical_data_timeout_seconds": 10},
            "breakout": {"bar_size_seconds": 5},
            "gex": {
                "provider_type": 1,
                "days_to_expiration": 10,
                "strikes_quantity": 3,
                "option_multiplier": 100
            },
            "trade_execution": {
                "take_profit_percentage": 1.0,
                "stop_loss_percentage": 0.5,
                "order_defaults": {"entry_order_type": "MKT", "tp_order_type": "LMT", "sl_order_type": "STP"}
            },
            "logging": {"log_level": "INFO", "log_file": "trading_bot.log"}
        }
        self.mock_config = AppConfig.parse_obj(self.full_mock_config)
        
        self.mock_connector = MagicMock()
        self.mock_connector.is_connected.return_value = True
        self.mock_connector.wrapper = MagicMock()
        
        # Give the mock wrapper actual Queue instances so get/put works
        self.mock_connector.wrapper.tick_price_queue = Queue()
        self.mock_connector.wrapper.sec_def_opt_params_queue = Queue()
        self.mock_connector.wrapper.option_greeks_queue = Queue()
        self.mock_connector.wrapper.tick_size_queue = Queue()

        # Mock request ID generation
        self.next_req_id = 0
        def get_next_req_id():
            self.next_req_id += 1
            return self.next_req_id
        self.mock_connector.get_next_request_id.side_effect = get_next_req_id


    def test_factory_returns_ib_provider(self):
        """
        Verify that the factory returns an IBProvider instance when provider_type is 1.
        """
        provider = get_gex_provider(self.mock_config)
        self.assertIsInstance(provider, IBProvider)
        self.assertIsInstance(provider, BaseGexProvider)

    def test_calculate_gex_logic(self):
        """
        Unit test the internal GEX calculation logic.
        """
        provider = IBProvider(self.mock_config)
        
        # Mock input data
        req_id_map = {
            1: {"strike": 4500, "right": "C"},
            2: {"strike": 4500, "right": "P"},
            3: {"strike": 4600, "right": "C"},
            4: {"strike": 4600, "right": "P"},
        }
        data_aggregator = {
            1: {"gamma": 0.05, "oi": 100}, # Call GEX = 0.05 * 100 * 100 = 500
            2: {"gamma": 0.04, "oi": 120}, # Put GEX = 0.04 * 120 * 100 = 480
            3: {"gamma": 0.06, "oi": 80},  # Call GEX = 0.06 * 80 * 100 = 480
            4: {"gamma": 0.07, "oi": 90},  # Put GEX = 0.07 * 90 * 100 = 630
        }
        # Expected: 4500 strike GEX = 500 + 480 = 980
        # Expected: 4600 strike GEX = 480 + 630 = 1110

        result = provider._calculate_gex(req_id_map, data_aggregator)

        self.assertIn(4500, result)
        self.assertIn(4600, result)
        self.assertAlmostEqual(result[4500], 980)
        self.assertAlmostEqual(result[4600], 1110)

    @patch('strategy.gex.ib_provider.datetime')
    def test_get_max_gamma_strike_e2e(self, mock_datetime):
        """
        End-to-end test for the main `get_max_gamma_strike` method.
        """
        # --- Arrange ---
        # 1. Mock time
        mock_datetime.now.return_value = datetime(2023, 1, 1)
        target_date = datetime(2023, 1, 1) + timedelta(days=self.mock_config.gex.days_to_expiration)
        target_expiration_str = target_date.strftime("%Y%m%d")

        # 2. Mock IBConnector responses
        mock_details = ContractDetails()
        mock_details.contract = Contract()
        mock_details.contract.conId = 12345
        self.mock_connector.resolve_contract_details.return_value = mock_details
        
        self.mock_connector.wrapper.tick_price_queue.put((1, 4, 4552.0, None)) # Underlying price
        self.mock_connector.wrapper.sec_def_opt_params_queue.put((2, {
            "expirations": [target_expiration_str, "20240101"],
            "strikes": [4500.0, 4550.0, 4600.0, 4650.0]
        }))
        
        # Market data responses (gamma and OI)
        # Using side_effect to feed items from a list to the mock queue
        greek_data = [
            (4, {"gamma": 0.05}), (5, {"gamma": 0.04}), # Strike 4550
            (6, {"gamma": 0.06}), (7, {"gamma": 0.07})  # Strike 4600
        ]
        oi_data = [
            (4, 27, 100), (5, 28, 120), # Strike 4550 (Call OI, Put OI)
            (6, 27, 80),  (7, 28, 90)   # Strike 4600 (Call OI, Put OI)
        ]
        self.mock_connector.wrapper.option_greeks_queue.get_nowait.side_effect = greek_data + [Empty]
        self.mock_connector.wrapper.tick_size_queue.get_nowait.side_effect = oi_data + [Empty]
        
        # --- Act ---
        provider = IBProvider(self.mock_config)
        result_strike, result_exp = provider.get_max_gamma_strike("SPX", self.mock_connector)

        # --- Assert ---
        # Expected GEX:
        # Strike 4550: (0.05 * 100 * 100) + (0.04 * 120 * 100) = 500 + 480 = 980
        # Strike 4600: (0.06 * 80 * 100) + (0.07 * 90 * 100) = 480 + 630 = 1110
        # Max GEX is at strike 4600
        self.assertEqual(result_strike, 4600.0)
        self.assertEqual(result_exp, target_expiration_str)

        # Verify cancellations were called for all market data requests
        self.assertEqual(self.mock_connector.cancel_market_data.call_count, 4) # 2 strikes * 2 (C/P)
        self.mock_connector.cancel_market_data.assert_has_calls([call(4), call(5), call(6), call(7)], any_order=True)

    def test_connector_not_connected(self):
        """Test graceful exit if connector is not connected."""
        self.mock_connector.is_connected.return_value = False
        provider = IBProvider(self.mock_config)
        result = provider.get_max_gamma_strike("SPX", self.mock_connector)
        self.assertEqual(result, (0.0, ""))

    def test_contract_resolution_fails(self):
        """Test graceful exit if contract resolution fails."""
        self.mock_connector.resolve_contract_details.return_value = None
        provider = IBProvider(self.mock_config)
        result = provider.get_max_gamma_strike("SPX", self.mock_connector)
        self.assertEqual(result, (0.0, ""))

    def test_data_collection_timeout(self):
        """Test that the method completes even if data collection times out."""
        # --- Arrange ---
        # Simulate a full set of API responses, but make the data collection loop timeout
        # by providing no data to the queues.
        mock_details = ContractDetails()
        mock_details.contract = Contract()
        mock_details.contract.conId = 12345
        self.mock_connector.resolve_contract_details.return_value = mock_details
        self.mock_connector.wrapper.tick_price_queue.put((1, 4, 4552.0, None))
        self.mock_connector.wrapper.sec_def_opt_params_queue.put((2, {
            "expirations": ["20230111"], "strikes": [4550.0, 4600.0]
        }))

        # Queues are empty, forcing a timeout in _collect_market_data
        self.mock_connector.wrapper.option_greeks_queue.get_nowait.side_effect = Empty
        self.mock_connector.wrapper.tick_size_queue.get_nowait.side_effect = Empty

        # --- Act ---
        with patch('strategy.gex.ib_provider.logger') as mock_logger:
            provider = IBProvider(self.mock_config)
            # Patch the timeout to be very short for the test
            provider._collect_market_data = MagicMock()
            provider._collect_market_data.side_effect = lambda conn, num, agg: self.original_collect(provider, conn, num, agg, timeout=1)
            
            # The original method is needed to patch its timeout
            self.original_collect = provider._collect_market_data

            result_strike, result_exp = provider.get_max_gamma_strike("SPX", self.mock_connector)

            # --- Assert ---
            # Should return default because no GEX was calculated
            self.assertEqual(result_strike, 0.0)
            self.assertEqual(result_exp, "")
            # And it should have logged a warning
            self.assertTrue(any("Market data collection timed out" in str(c) for c in mock_logger.warning.call_args_list))

if __name__ == '__main__':
    unittest.main()
