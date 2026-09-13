from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from src.auth import AuthManager, UserStore
from src.dashboard import create_app
from src.enterprise_auth import OIDCSettings
from tests.test_dashboard import build_services


class FakeOIDCClient:
    def __init__(self) -> None:
        self.settings = OIDCSettings(
            issuer="https://login.example.com",
            client_id="client-id",
            client_secret="client-secret",
            redirect_uri="http://testserver/api/auth/sso/callback",
            default_role="operator",
            enabled=True,
        )
        self.is_enabled = True

    def build_authorization_url(self, state: str, nonce: str) -> str:
        return f"https://login.example.com/authorize?state={state}&nonce={nonce}"

    def load_profile(self, code: str, nonce: str) -> SimpleNamespace:
        assert code == "valid-code"
        assert nonce == "nonce-123"
        return SimpleNamespace(
            issuer="https://login.example.com",
            subject="subject-123",
            email="ops@example.com",
            display_name="Ops Lead",
            claims={"sub": "subject-123", "email": "ops@example.com", "nonce": nonce},
        )


def enable_oidc_env(monkeypatch) -> None:
    monkeypatch.setenv("AEGISNEX_OIDC_ISSUER", "https://login.example.com")
    monkeypatch.setenv("AEGISNEX_OIDC_CLIENT_ID", "client-id")
    monkeypatch.setenv("AEGISNEX_OIDC_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("AEGISNEX_OIDC_REDIRECT_URI", "http://testserver/api/auth/sso/callback")


def make_app(tmp_path: Path):
    auth_manager = AuthManager(
        user_store=UserStore(tmp_path / "users.db"),
        jwt_secret="test-secret-32chars-long-please!",
    )
    app = create_app(
        services=build_services(tmp_path),
        auth_manager=auth_manager,
        telemetry_db_path=str(tmp_path / "telemetry.db"),
    )
    return app


def test_sso_config_reports_disabled_when_env_is_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("AEGISNEX_DEMO_ENABLED", raising=False)
    monkeypatch.delenv("AEGISNEX_DEMO_AUTH_ENABLED", raising=False)
    app = make_app(tmp_path)
    client = TestClient(app)

    response = client.get("/api/auth/sso/config")

    assert response.status_code == 200
    assert response.json()["enabled"] is False
    assert response.json()["local_auth_enabled"] is True
    # Demo login is opt-in only and off by default in every environment.
    assert response.json()["demo_auth_enabled"] is False


def test_sso_login_redirect_sets_state_and_nonce_cookies(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    app.state.oidc_client = FakeOIDCClient()
    client = TestClient(app)

    response = client.get("/api/auth/sso/login", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"].startswith("https://login.example.com/authorize")
    assert "aegisnex_oidc_state" in response.headers["set-cookie"]
    assert "aegisnex_oidc_nonce" in response.headers["set-cookie"]


def test_sso_callback_provisions_user_and_sets_session_cookie(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    app.state.oidc_client = FakeOIDCClient()
    client = TestClient(app)
    client.cookies.set("aegisnex_oidc_state", "state-123")
    client.cookies.set("aegisnex_oidc_nonce", "nonce-123")

    response = client.get(
        "/api/auth/sso/callback?code=valid-code&state=state-123",
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"].endswith("/dashboard")
    assert "aegisnex_session" in response.headers["set-cookie"]
    assert app.state.auth_manager.user_store.get_user_by_email("ops@example.com") is not None


def test_production_requires_sso_or_explicit_local_auth(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AEGISNEX_ENV", "production")
    auth_manager = AuthManager(
        user_store=UserStore(tmp_path / "users.db"),
        jwt_secret="test-secret-32chars-long-please!",
    )

    try:
        create_app(
            services=build_services(tmp_path),
            auth_manager=auth_manager,
            telemetry_db_path=str(tmp_path / "telemetry.db"),
        )
        assert False, "create_app should reject production without configured auth"
    except RuntimeError as exc:
        assert "Production auth is not configured" in str(exc)


def test_production_does_not_seed_default_admin(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AEGISNEX_ENV", "production")
    enable_oidc_env(monkeypatch)
    auth_manager = AuthManager(
        user_store=UserStore(tmp_path / "users.db"),
        jwt_secret="test-secret-32chars-long-please!",
    )

    app = create_app(
        services=build_services(tmp_path),
        auth_manager=auth_manager,
        telemetry_db_path=str(tmp_path / "telemetry.db"),
    )

    assert app.state.auth_manager.user_store.get_user_by_email("admin") is None


def test_production_blocks_password_and_demo_login_by_default(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AEGISNEX_ENV", "production")
    monkeypatch.delenv("AEGISNEX_DEMO_ENABLED", raising=False)
    monkeypatch.delenv("AEGISNEX_DEMO_AUTH_ENABLED", raising=False)
    enable_oidc_env(monkeypatch)
    app = make_app(tmp_path)
    client = TestClient(app, base_url="https://testserver", client=("prod-auth-test", 50000))

    password_response = client.post("/api/login", data={"username": "admin", "password": "anything"})
    demo_response = client.post("/api/auth/demo-login")
    config_response = client.get("/api/auth/sso/config")

    assert password_response.status_code == 404
    assert demo_response.status_code == 404
    assert config_response.json()["enabled"] is True
    assert config_response.json()["local_auth_enabled"] is False
    assert config_response.json()["demo_auth_enabled"] is False


def test_production_requires_org_membership_for_non_admin_user(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AEGISNEX_ENV", "production")
    enable_oidc_env(monkeypatch)
    auth_manager = AuthManager(
        user_store=UserStore(tmp_path / "users.db"),
        jwt_secret="test-secret-32chars-long-please!",
    )
    user, token, _ = auth_manager.external_login(
        provider="https://login.example.com",
        subject="subject-tenantless",
        email="tenantless@example.com",
        role="operator",
    )
    app = create_app(
        services=build_services(tmp_path),
        auth_manager=auth_manager,
        telemetry_db_path=str(tmp_path / "telemetry.db"),
    )
    client = TestClient(app, base_url="https://testserver")

    response = client.get("/api/auth/verify", headers={"Authorization": f"Bearer {token}"})

    assert user.is_superuser is False
    assert response.status_code == 403
    assert response.json()["detail"] == "User is not assigned to an organization"


def test_bootstrap_admin_email_becomes_super_admin_without_org_membership(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AEGISNEX_ENV", "production")
    monkeypatch.setenv("AEGISNEX_BOOTSTRAP_ADMIN_EMAILS", "ops@example.com")
    enable_oidc_env(monkeypatch)
    app = make_app(tmp_path)
    app.state.oidc_client = FakeOIDCClient()
    client = TestClient(app, base_url="https://testserver")
    client.cookies.set("aegisnex_oidc_state", "state-123")
    client.cookies.set("aegisnex_oidc_nonce", "nonce-123")

    response = client.get(
        "/api/auth/sso/callback?code=valid-code&state=state-123",
        follow_redirects=False,
    )

    user = app.state.auth_manager.user_store.get_user_by_email("ops@example.com")
    assert response.status_code == 302
    assert user is not None
    assert user.role == "super_admin"
    assert user.is_superuser is True
