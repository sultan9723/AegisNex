import src.integrations.marketplace
import src.integrations.providers  # noqa: F401 — registers all integrations
from src.integrations.base import (
    INTEGRATION_REGISTRY,
    IntegrationConfig,
    IntegrationProvider,
    IntegrationResult,
    get_integration,
    list_integrations,
    register_integration,
)
from src.integrations.marketplace import (
    get_installed_integrations,
    get_marketplace_catalog,
    install_integration,
    uninstall_integration,
)

__all__ = [
    "INTEGRATION_REGISTRY",
    "IntegrationConfig",
    "IntegrationProvider",
    "IntegrationResult",
    "get_installed_integrations",
    "get_integration",
    "get_marketplace_catalog",
    "install_integration",
    "list_integrations",
    "register_integration",
    "uninstall_integration",
]
