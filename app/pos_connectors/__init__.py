"""
POS Connectors Package.
Provides a unified interface for different POS systems.
"""

from .base import BasePOSConnector
from .toast_connector import ToastConnector
from .square_connector import SquareConnector

# Registry of available POS connectors
CONNECTOR_REGISTRY = {
    'toast': ToastConnector,
    'square': SquareConnector,
}

# Human-readable names for UI
PROVIDER_NAMES = {
    'toast': 'Toast',
    'square': 'Square',
}


def get_connector(provider_name, credentials):
    """
    Get a POS connector instance for the given provider.
    
    Args:
        provider_name: str - 'toast', 'square', etc.
        credentials: dict - Contains access_token, refresh_token, location_id
        
    Returns:
        BasePOSConnector subclass instance
        
    Raises:
        NotImplementedError if provider not supported
    """
    if not provider_name:
        raise ValueError("No POS provider specified")
    
    provider_key = provider_name.lower()
    
    if provider_key not in CONNECTOR_REGISTRY:
        raise NotImplementedError(
            f"POS provider '{provider_name}' is not supported. "
            f"Available: {list(CONNECTOR_REGISTRY.keys())}"
        )
    
    connector_class = CONNECTOR_REGISTRY[provider_key]
    return connector_class(credentials)
