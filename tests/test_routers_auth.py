"""Tests for authentication router."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from src.routers.auth import (
    _clear_auth_cookies,
    _set_auth_cookie,
    _set_refresh_cookie,
)


def test_set_auth_cookie():
    """Test setting authentication cookie."""
    response = MagicMock()
    _set_auth_cookie(response, "test_token", 3600)
    response.set_cookie.assert_called_once_with(
        key="aegisnex_session",
        value="test_token",
        max_age=3600,
        httponly=True,
        secure=False,
        samesite="lax",
    )


def test_set_refresh_cookie():
    """Test setting refresh cookie."""
    response = MagicMock()
    _set_refresh_cookie(response, "refresh_token", 86400)
    response.set_cookie.assert_called_once_with(
        key="aegisnex_refresh",
        value="refresh_token",
        max_age=86400,
        httponly=True,
        secure=False,
        samesite="lax",
    )


def test_clear_auth_cookies():
    """Test clearing authentication cookies."""
    response = MagicMock()
    _clear_auth_cookies(response)
    assert response.delete_cookie.call_count == 2
    response.delete_cookie.assert_any_call(key="aegisnex_session")
    response.delete_cookie.assert_any_call(key="aegisnex_refresh")


def test_login_request_schema():
    """Test login request validation."""
    from pydantic import ValidationError

    from src.routers.auth import LoginRequest

    # Valid request
    req = LoginRequest(username="admin", password="password123")
    assert req.username == "admin"
    assert req.password == "password123"

    # Empty username should fail
    with pytest.raises(ValidationError):
        LoginRequest(username="", password="password123")

    # Empty password should fail
    with pytest.raises(ValidationError):
        LoginRequest(username="admin", password="")
