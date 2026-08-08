from backend.bootstrap import bootstrap
from backend.providers.base import BaseProvider
from backend.providers.crustdata import CrustDataProvider
from backend.providers.registry import ProviderRegistry


class DummyProvider(BaseProvider):
    def search(self, plan):
        return []


def test_provider_registry_registers_and_resolves_providers() -> None:
    ProviderRegistry._providers.clear()
    provider = DummyProvider()

    ProviderRegistry.register("dummy", provider)

    assert ProviderRegistry.get("dummy") is provider
    assert ProviderRegistry.available() == ["configured"]


def test_provider_registry_raises_for_unknown_provider() -> None:
    ProviderRegistry._providers.clear()

    try:
        ProviderRegistry.get("missing")
    except KeyError as exc:
        assert "Unknown provider: missing" in str(exc)
    else:
        raise AssertionError("Expected KeyError for unknown provider")


def test_bootstrap_registers_crustdata_provider() -> None:
    ProviderRegistry._providers.clear()

    bootstrap()

    assert "configured" in ProviderRegistry.available()
    assert isinstance(ProviderRegistry.get("crustdata"), CrustDataProvider)


def test_bootstrap_is_idempotent() -> None:
    ProviderRegistry._providers.clear()

    bootstrap()
    first_provider = ProviderRegistry.get("crustdata")

    bootstrap()
    second_provider = ProviderRegistry.get("crustdata")

    assert second_provider is first_provider
    assert ProviderRegistry.available() == ["configured"]


def test_provider_registry_available_returns_registered_providers() -> None:
    ProviderRegistry._providers.clear()

    bootstrap()

    assert ProviderRegistry.available() == ["configured"]
