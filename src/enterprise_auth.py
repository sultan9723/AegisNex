"""Enterprise SSO helpers for OIDC-compatible identity providers."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt as pyjwt

NON_PRODUCTION_ENVS = {"development", "dev", "local", "test"}


class OIDCConfigurationError(RuntimeError):
    """Raised when OIDC is requested but not configured correctly."""


@dataclass(frozen=True)
class OIDCSettings:
    issuer: str
    client_id: str
    client_secret: str
    redirect_uri: str
    scopes: str = "openid email profile"
    default_role: str = "read_only"
    allowed_domains: tuple[str, ...] = ()
    enabled: bool = False

    @classmethod
    def from_env(cls) -> OIDCSettings:
        issuer = os.getenv("AEGISNEX_OIDC_ISSUER", "").strip().rstrip("/")
        client_id = os.getenv("AEGISNEX_OIDC_CLIENT_ID", "").strip()
        client_secret = os.getenv("AEGISNEX_OIDC_CLIENT_SECRET", "").strip()
        redirect_uri = os.getenv("AEGISNEX_OIDC_REDIRECT_URI", "").strip()
        domains = tuple(
            domain.strip().lower()
            for domain in os.getenv("AEGISNEX_SSO_ALLOWED_DOMAINS", "").split(",")
            if domain.strip()
        )
        enabled = all((issuer, client_id, client_secret, redirect_uri))
        return cls(
            issuer=issuer,
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scopes=os.getenv("AEGISNEX_OIDC_SCOPES", "openid email profile").strip()
            or "openid email profile",
            default_role=os.getenv("AEGISNEX_OIDC_DEFAULT_ROLE", "read_only").strip()
            or "read_only",
            allowed_domains=domains,
            enabled=enabled,
        )

    def require_enabled(self) -> None:
        if not self.enabled:
            raise OIDCConfigurationError(
                "Enterprise SSO is not configured. Set AEGISNEX_OIDC_ISSUER, "
                "AEGISNEX_OIDC_CLIENT_ID, AEGISNEX_OIDC_CLIENT_SECRET, and "
                "AEGISNEX_OIDC_REDIRECT_URI."
            )


@dataclass(frozen=True)
class OIDCDiscovery:
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str
    userinfo_endpoint: str | None = None


@dataclass(frozen=True)
class OIDCProfile:
    subject: str
    email: str
    display_name: str
    issuer: str
    claims: dict[str, Any]


class OIDCClient:
    def __init__(self, settings: OIDCSettings | None = None) -> None:
        self.settings = settings or OIDCSettings.from_env()

    @property
    def is_enabled(self) -> bool:
        return self.settings.enabled

    def discover(self) -> OIDCDiscovery:
        self.settings.require_enabled()
        url = f"{self.settings.issuer}/.well-known/openid-configuration"
        response = httpx.get(url, timeout=10)
        response.raise_for_status()
        payload = response.json()
        return OIDCDiscovery(
            authorization_endpoint=str(payload["authorization_endpoint"]),
            token_endpoint=str(payload["token_endpoint"]),
            jwks_uri=str(payload["jwks_uri"]),
            userinfo_endpoint=payload.get("userinfo_endpoint"),
        )

    def build_authorization_url(self, state: str, nonce: str) -> str:
        discovery = self.discover()
        params = {
            "client_id": self.settings.client_id,
            "redirect_uri": self.settings.redirect_uri,
            "response_type": "code",
            "scope": self.settings.scopes,
            "state": state,
            "nonce": nonce,
        }
        return f"{discovery.authorization_endpoint}?{urlencode(params)}"

    def exchange_code(self, code: str) -> dict[str, Any]:
        discovery = self.discover()
        response = httpx.post(
            discovery.token_endpoint,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.settings.redirect_uri,
                "client_id": self.settings.client_id,
                "client_secret": self.settings.client_secret,
            },
            headers={"Accept": "application/json"},
            timeout=15,
        )
        response.raise_for_status()
        return response.json()

    def verify_id_token(self, id_token: str, nonce: str) -> dict[str, Any]:
        discovery = self.discover()
        header = pyjwt.get_unverified_header(id_token)
        kid = header.get("kid")
        jwks_response = httpx.get(discovery.jwks_uri, timeout=10)
        jwks_response.raise_for_status()
        jwks = jwks_response.json()
        key = None
        for candidate in jwks.get("keys", []):
            if candidate.get("kid") == kid:
                key = pyjwt.algorithms.RSAAlgorithm.from_jwk(candidate)
                break
        if key is None:
            raise OIDCConfigurationError("OIDC signing key was not found in JWKS.")

        claims = pyjwt.decode(
            id_token,
            key=key,
            algorithms=["RS256"],
            audience=self.settings.client_id,
            issuer=self.settings.issuer,
            options={"require": ["sub", "exp", "iat"]},
        )
        if claims.get("nonce") != nonce:
            raise OIDCConfigurationError("OIDC nonce validation failed.")
        return dict(claims)

    def load_profile(self, code: str, nonce: str) -> OIDCProfile:
        tokens = self.exchange_code(code)
        id_token = tokens.get("id_token")
        if not id_token:
            raise OIDCConfigurationError("OIDC provider did not return an ID token.")
        claims = self.verify_id_token(str(id_token), nonce)
        email = str(claims.get("email", "")).strip().lower()
        if not email:
            raise OIDCConfigurationError("OIDC profile did not include an email address.")
        if self.settings.allowed_domains:
            domain = email.rsplit("@", 1)[-1]
            if domain not in self.settings.allowed_domains:
                raise OIDCConfigurationError("Email domain is not allowed for this workspace.")
        subject = str(claims.get("sub", ""))
        display_name = str(claims.get("name") or claims.get("preferred_username") or email)
        return OIDCProfile(
            subject=subject,
            email=email,
            display_name=display_name,
            issuer=self.settings.issuer,
            claims=claims,
        )


def new_oidc_state() -> str:
    return secrets.token_urlsafe(32)


def new_oidc_nonce() -> str:
    return secrets.token_urlsafe(32)


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def current_environment() -> str:
    return os.getenv("AEGISNEX_ENV", "development").strip().lower()


def is_production_environment() -> bool:
    return current_environment() not in NON_PRODUCTION_ENVS


def env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def local_auth_enabled() -> bool:
    if is_production_environment():
        return env_flag("AEGISNEX_LOCAL_AUTH_ENABLED", False)
    return env_flag("AEGISNEX_LOCAL_AUTH_ENABLED", True)


def demo_auth_enabled() -> bool:
    """Demo login is opt-in only, off by default in every environment.

    Unlike local_auth_enabled()/seed_default_admin_enabled(), this has no
    dev-mode default and no production block: it must work in production
    (Azure) when explicitly enabled, since the demo login issues a
    restricted, non-admin session rather than real credentials.
    """
    # AEGISNEX_DEMO_AUTH_ENABLED was the original documented name. Keep it
    # as a compatibility alias so existing deployments do not silently hide
    # the demo after upgrading; the canonical name remains AEGISNEX_DEMO_ENABLED.
    return env_flag(
        "AEGISNEX_DEMO_ENABLED",
        env_flag("AEGISNEX_DEMO_AUTH_ENABLED", False),
    )


def seed_default_admin_enabled() -> bool:
    if is_production_environment():
        return env_flag("AEGISNEX_SEED_DEFAULT_ADMIN", False)
    return env_flag("AEGISNEX_SEED_DEFAULT_ADMIN", True)


def tenant_membership_required() -> bool:
    if is_production_environment():
        return env_flag("AEGISNEX_REQUIRE_TENANT_MEMBERSHIP", True)
    return env_flag("AEGISNEX_REQUIRE_TENANT_MEMBERSHIP", False)


def bootstrap_admin_emails() -> set[str]:
    return {
        email.strip().lower()
        for email in os.getenv("AEGISNEX_BOOTSTRAP_ADMIN_EMAILS", "").split(",")
        if email.strip()
    }


def sso_role_for_email(email: str, default_role: str) -> str:
    if email.strip().lower() in bootstrap_admin_emails():
        return "super_admin"
    return default_role


def sso_auto_create_orgs_enabled() -> bool:
    return env_flag("AEGISNEX_SSO_AUTO_CREATE_ORGS", False)
