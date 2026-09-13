"""Tests for CSRF middleware."""

from __future__ import annotations

import secrets
from unittest.mock import MagicMock, patch

import pytest

from src.middleware.csrf import CSRFMiddleware


def test_csrf_middleware_generates_token():
    """Test CSRF token generation."""
    middleware = CSRFMiddleware(MagicMock())
    token = middleware._generate_token()
    assert isinstance(token, str)
    assert len(token) > 0


def test_csrf_middleware_validates_token():
    """Test CSRF token validation."""
    middleware = CSRFMiddleware(MagicMock())
    token = middleware._generate_token()
    assert middleware._token_is_valid(token, token) is True


def test_csrf_middleware_rejects_invalid_token():
    """Test CSRF middleware rejects invalid tokens."""
    middleware = CSRFMiddleware(MagicMock())
    token = middleware._generate_token()
    wrong_token = middleware._generate_token()
    assert middleware._token_is_valid(token, wrong_token) is False


def test_csrf_middleware_rejects_empty_token():
    """Test CSRF middleware rejects empty tokens."""
    middleware = CSRFMiddleware(MagicMock())
    assert middleware._token_is_valid("", "token") is False
    assert middleware._token_is_valid("token", "") is False
    assert middleware._token_is_valid("", "") is False


def test_csrf_exempt_paths():
    """Test that exempt paths are correctly defined."""
    middleware = CSRFMiddleware(MagicMock())
    assert "/api/health" in middleware.EXEMPT_PATHS
    assert "/api/auth/login" in middleware.EXEMPT_PATHS
    assert "/api/auth/demo-login" in middleware.EXEMPT_PATHS


def test_csrf_protected_methods():
    """Test that protected methods are correctly defined."""
    middleware = CSRFMiddleware(MagicMock())
    assert "POST" in middleware.PROTECTED_METHODS
    assert "PUT" in middleware.PROTECTED_METHODS
    assert "PATCH" in middleware.PROTECTED_METHODS
    assert "DELETE" in middleware.PROTECTED_METHODS
    assert "GET" not in middleware.PROTECTED_METHODS
