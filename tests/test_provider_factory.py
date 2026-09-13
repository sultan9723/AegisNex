"""Tests for the provider factory's Groq support (reuses OpenAIProvider)."""

from __future__ import annotations

import pytest

from src.intelligence.providers.factory import (
    _GROQ_DEFAULT_BASE_URL,
    create_provider,
    get_default_provider,
)


def test_get_default_provider_reads_env(monkeypatch) -> None:
    monkeypatch.setenv("AEGIS_AI_PROVIDER", "groq")
    assert get_default_provider() == "groq"


def test_get_default_provider_defaults_to_openai(monkeypatch) -> None:
    monkeypatch.delenv("AEGIS_AI_PROVIDER", raising=False)
    assert get_default_provider() == "openai"


def test_groq_reuses_openai_provider_class(monkeypatch) -> None:
    monkeypatch.setenv("AEGIS_AI_GROQ_API_KEY", "test-key-not-real")
    monkeypatch.setenv("AEGIS_AI_GROQ_MODEL", "openai/gpt-oss-20b")
    monkeypatch.delenv("AEGIS_AI_GROQ_BASE_URL", raising=False)

    provider = create_provider(name="groq")

    from src.intelligence.providers.openai_provider import OpenAIProvider
    assert isinstance(provider, OpenAIProvider)
    assert provider.config.base_url == _GROQ_DEFAULT_BASE_URL
    assert provider.config.model == "openai/gpt-oss-20b"


def test_groq_base_url_env_override_wins(monkeypatch) -> None:
    monkeypatch.setenv("AEGIS_AI_GROQ_API_KEY", "test-key-not-real")
    monkeypatch.setenv("AEGIS_AI_GROQ_BASE_URL", "https://custom.example.com/v1")

    provider = create_provider(name="groq")

    assert provider.config.base_url == "https://custom.example.com/v1"


def test_unknown_provider_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Unknown AI provider"):
        create_provider(name="not-a-real-provider")
