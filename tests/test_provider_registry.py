from backend.providers.base import BaseProvider
from backend.providers.registry import ProviderRegistry


class DummyProvider(BaseProvider):
    def search(self, plan):
        return []


def test_provider_registry_registers_and_resolves_providers() -> None:
    ProviderRegistry._providers.clear()
    provider = DummyProvider()

    ProviderRegistry.register("dummy", provider)

    assert ProviderRegistry.get("dummy") is provider
    assert ProviderRegistry.available() == ["dummy"]


def test_provider_registry_raises_for_unknown_provider() -> None:
    ProviderRegistry._providers.clear()

    try:
        ProviderRegistry.get("missing")
    except KeyError as exc:
        assert "Unknown provider: missing" in str(exc)
    else:
        raise AssertionError("Expected KeyError for unknown provider")
