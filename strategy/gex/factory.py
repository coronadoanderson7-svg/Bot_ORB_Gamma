# strategy/gex/factory.py

from core.config_loader import AppConfig
from .base_provider import BaseGexProvider
from .gexbot_provider import GexbotProvider
from .ib_provider import IBProvider
from .massive_data_provider import MassiveDataProvider

def get_gex_provider(config: AppConfig) -> BaseGexProvider:
    """
    Factory function to get the appropriate GEX provider based on config.

    Args:
        config: The application's configuration object.

    Returns:
        An instance of a class that implements BaseGexProvider.
    """
    provider_type = config.gex.provider_type

    if provider_type == 0:
        return GexbotProvider(config)
    elif provider_type == 1:
        return IBProvider(config)
    elif provider_type == 2:
        return MassiveDataProvider(config)
    else:
        raise ValueError(f"Invalid provider_type in config: {provider_type}")