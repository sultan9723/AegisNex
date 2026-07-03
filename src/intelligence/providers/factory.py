from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from src.intelligence.providers.base import ModelProvider, ProviderConfig

_PROVIDER_NAMES = ["openai", "ollama", "anthropic", "gemini", "azure"]
_DEFAULT_PROVIDER = "openai"


def _load_config_from_env(provider: str) -> ProviderConfig:
    prefix = f"AEGIS_AI_{provider.upper()}"
    return ProviderConfig(
        model=os.getenv(f"{prefix}_MODEL", ""),
        temperature=float(os.getenv(f"{prefix}_TEMPERATURE", "0.3")),
        max_tokens=int(os.getenv(f"{prefix}_MAX_TOKENS", "2048")),
        api_key=os.getenv(f"{prefix}_API_KEY") or os.getenv(f"{prefix}_KEY"),
        base_url=os.getenv(f"{prefix}_BASE_URL"),
        organization=os.getenv(f"{prefix}_ORGANIZATION"),
        deployment_name=os.getenv(f"{prefix}_DEPLOYMENT"),
    )


def create_provider(name: Optional[str] = None, config: Optional[ProviderConfig] = None) -> ModelProvider:
    resolved = (name or os.getenv("AEGIS_AI_PROVIDER", _DEFAULT_PROVIDER)).strip().lower()
    cfg = config or _load_config_from_env(resolved)

    if resolved == "openai":
        from src.intelligence.providers.openai_provider import OpenAIProvider
        return OpenAIProvider(cfg)
    elif resolved == "ollama":
        from src.intelligence.providers.ollama_provider import OllamaProvider
        return OllamaProvider(cfg)
    elif resolved == "anthropic":
        from src.intelligence.providers.anthropic_provider import AnthropicProvider
        return AnthropicProvider(cfg)
    elif resolved == "gemini":
        from src.intelligence.providers.gemini_provider import GeminiProvider
        return GeminiProvider(cfg)
    elif resolved == "azure":
        from src.intelligence.providers.azure_provider import AzureProvider
        return AzureProvider(cfg)
    else:
        raise ValueError(f"Unknown AI provider: {resolved}. Supported: {', '.join(_PROVIDER_NAMES)}")


def get_provider_names() -> List[str]:
    return list(_PROVIDER_NAMES)


def get_default_provider() -> str:
    return os.getenv("AEGIS_AI_PROVIDER", _DEFAULT_PROVIDER)
