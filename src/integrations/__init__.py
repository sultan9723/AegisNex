import src.integrations.providers  # noqa: F401 — registers all integrations
import src.integrations.marketplace  # noqa: F401 — ensures marketplace is loaded

from src.integrations.base import (
    IntegrationProvider,
    IntegrationConfig,
    IntegrationResult,
    INTEGRATION_REGISTRY,
    register_integration,
    get_integration,
    list_integrations,
)
from src.integrations.marketplace import (
    get_marketplace_catalog,
    install_integration,
    uninstall_integration,
    get_installed_integrations,
)

__all__ = [
    "IntegrationProvider",
    "IntegrationConfig",
    "IntegrationResult",
    "INTEGRATION_REGISTRY",
    "register_integration",
    "get_integration",
    "list_integrations",
    "get_marketplace_catalog",
    "install_integration",
    "uninstall_integration",
    "get_installed_integrations",
]
