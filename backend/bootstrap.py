from backend.providers.crustdata import CrustDataProvider
from backend.providers.registry import ProviderRegistry


def bootstrap() -> None:
    """Register built-in providers with the shared registry once."""
    providers = {
        "crustdata": CrustDataProvider(),
    }

    for name, provider in providers.items():
        if name not in ProviderRegistry._providers:
            ProviderRegistry.register(name, provider)
