from typing import Dict, Optional, TypeVar

from backend.providers.base import BaseProvider

T = TypeVar("T", bound=BaseProvider)


class ProviderRegistry:
    """Registry for provider implementations that can be resolved by name."""

    _providers: Dict[str, BaseProvider] = {}

    @classmethod
    def register(cls, name: str, provider: BaseProvider) -> None:
        cls._providers[name] = provider

    @classmethod
    def get(cls, name: str) -> BaseProvider:
        provider = cls._providers.get(name)
        if provider is None:
            raise KeyError(f"Unknown provider: {name}")
        return provider

    @classmethod
    def available(cls) -> list[str]:
        return ["configured"] if cls._providers else []
