# tests/strategy/gex/test_factory.py

import unittest

from core.config_loader import Config
from strategy.gex.factory import get_gex_provider
from strategy.gex.gexbot_provider import GexbotProvider
from strategy.gex.massive_data_provider import MassiveDataProvider
from strategy.gex.base_provider import BaseGexProvider

class TestGexProviderFactory(unittest.TestCase):

    def test_get_gexbot_provider(self):
        """Test that provider_type 0 returns a GexbotProvider instance."""
        mock_config = Config.parse_obj({
            "gex": {
                "provider_type": 0,
                "providers": { # Needed for provider initialization
                    "gexbot": {"base_url": "test", "api_key": "test"}
                }
            }
        })
        provider = get_gex_provider(mock_config)
        self.assertIsInstance(provider, GexbotProvider)
        self.assertIsInstance(provider, BaseGexProvider)

    def test_get_massive_data_provider(self):
        """Test that provider_type 2 returns a MassiveDataProvider instance."""
        mock_config = Config.parse_obj({
            "gex": {
                "provider_type": 2,
                "providers": { # Needed for provider initialization
                    "massive_data": {"base_url": "test", "api_key": "test"}
                }
            }
        })
        provider = get_gex_provider(mock_config)
        self.assertIsInstance(provider, MassiveDataProvider)
        self.assertIsInstance(provider, BaseGexProvider)

    def test_not_implemented_provider(self):
        """Test that provider_type 1 raises a NotImplementedError."""
        mock_config = Config.parse_obj({"gex": {"provider_type": 1}})
        with self.assertRaisesRegex(NotImplementedError, "GEX Microservice provider is not yet implemented."):
            get_gex_provider(mock_config)

    def test_invalid_provider(self):
        """Test that an invalid provider_type raises a ValueError."""
        invalid_type = 99
        mock_config = Config.parse_obj({"gex": {"provider_type": invalid_type}})
        with self.assertRaisesRegex(ValueError, f"Invalid provider_type in config: {invalid_type}"):
            get_gex_provider(mock_config)

if __name__ == '__main__':
    unittest.main()