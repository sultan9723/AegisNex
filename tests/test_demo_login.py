import logging
from pathlib import Path

from fastapi.testclient import TestClient

from src.auth import AuthManager, UserStore
from src.dashboard import create_app
from src.platform_db import PlatformRepository
from tests.test_dashboard import build_services
from tests.test_enterprise_auth_routes import enable_oidc_env


def make_app(tmp_path: Path):
    auth_manager = AuthManager(
        user_store=UserStore(tmp_path / "users.db"),
        jwt_secret="test-secret-32chars-long-please!",
    )
    return create_app(
        services=build_services(tmp_path),
        auth_manager=auth_manager,
        telemetry_db_path=str(tmp_path / "telemetry.db"),
    )


def test_demo_login_disabled_by_default(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("AEGISNEX_DEMO_ENABLED", raising=False)
    monkeypatch.delenv("AEGISNEX_DEMO_AUTH_ENABLED", raising=False)
    app = make_app(tmp_path)
    client = TestClient(app, base_url="https://testserver")

    response = client.post("/api/auth/demo-login")

    assert response.status_code == 404


def test_legacy_demo_enabled_flag_remains_supported(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("AEGISNEX_DEMO_ENABLED", raising=False)
    monkeypatch.setenv("AEGISNEX_DEMO_AUTH_ENABLED", "true")
    monkeypatch.setenv("AEGISNEX_DEMO_PASSWORD", "demo-secret-not-a-real-password")
    app = make_app(tmp_path)
    client = TestClient(app, base_url="https://testserver")

    response = client.post("/api/auth/demo-login")

    assert response.status_code == 200


def test_demo_login_requires_password_configured(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AEGISNEX_DEMO_ENABLED", "true")
    monkeypatch.delenv("AEGISNEX_DEMO_AUTH_ENABLED", raising=False)
    monkeypatch.delenv("AEGISNEX_DEMO_PASSWORD", raising=False)
    app = make_app(tmp_path)
    client = TestClient(app, base_url="https://testserver")

    response = client.post("/api/auth/demo-login")

    assert response.status_code == 503


class _RecordingHandler(logging.Handler):
    """Collects log records directly from the src.dashboard logger.

    src.dashboard.create_app() calls configure_logging(), which replaces
    every handler on the *root* logger - including pytest's caplog handler,
    which is attached there. A handler attached directly to the
    "src.dashboard" logger itself is unaffected by that root-handler
    replacement, so this is used instead of caplog for these two tests.
    """

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def test_demo_login_missing_password_logs_actionable_warning(tmp_path: Path, monkeypatch) -> None:
    """The 503 a client sees ("Demo login is not configured...") must be
    backed by a server-side log line naming the exact env var to set, so
    this doesn't stay a mystery 503 in production log output."""
    monkeypatch.setenv("AEGISNEX_DEMO_ENABLED", "true")
    monkeypatch.delenv("AEGISNEX_DEMO_AUTH_ENABLED", raising=False)
    monkeypatch.delenv("AEGISNEX_DEMO_PASSWORD", raising=False)
    app = make_app(tmp_path)
    client = TestClient(app, base_url="https://testserver")

    handler = _RecordingHandler()
    dashboard_logger = logging.getLogger("src.dashboard")
    dashboard_logger.addHandler(handler)
    try:
        response = client.post("/api/auth/demo-login")
    finally:
        dashboard_logger.removeHandler(handler)

    assert response.status_code == 503
    assert any("AEGISNEX_DEMO_PASSWORD" in record.getMessage() for record in handler.records)


def test_demo_login_misconfiguration_logged_at_startup(tmp_path: Path, monkeypatch) -> None:
    """Ops should see this in boot logs immediately on deploy, not only after
    the first failed demo-login request."""
    monkeypatch.setenv("AEGISNEX_DEMO_ENABLED", "true")
    monkeypatch.delenv("AEGISNEX_DEMO_AUTH_ENABLED", raising=False)
    monkeypatch.delenv("AEGISNEX_DEMO_PASSWORD", raising=False)

    handler = _RecordingHandler()
    dashboard_logger = logging.getLogger("src.dashboard")
    dashboard_logger.addHandler(handler)
    try:
        make_app(tmp_path)
    finally:
        dashboard_logger.removeHandler(handler)

    assert any("AEGISNEX_DEMO_PASSWORD" in record.getMessage() for record in handler.records)


def test_demo_login_enabled_issues_restricted_session(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AEGISNEX_DEMO_ENABLED", "true")
    monkeypatch.setenv("AEGISNEX_DEMO_PASSWORD", "demo-secret-not-a-real-password")
    app = make_app(tmp_path)
    client = TestClient(app, base_url="https://testserver")

    response = client.post("/api/auth/demo-login")
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"

    verify = client.get("/api/auth/verify")
    assert verify.status_code == 200
    user = verify.json()["user"]
    assert user["role"] == "read_only"
    assert user["is_superuser"] is False
    assert user["email"] != "admin"


def test_demo_login_never_grants_admin_even_if_username_overridden(tmp_path: Path, monkeypatch) -> None:
    # Regression guard: demo login must never resolve to the real admin
    # account, even if AEGISNEX_DEMO_USERNAME is misconfigured to "admin".
    monkeypatch.setenv("AEGISNEX_DEMO_ENABLED", "true")
    monkeypatch.setenv("AEGISNEX_DEMO_USERNAME", "admin")
    monkeypatch.setenv("AEGISNEX_DEMO_PASSWORD", "demo-secret-not-a-real-password")
    app = make_app(tmp_path)
    client = TestClient(app, base_url="https://testserver")

    response = client.post("/api/auth/demo-login")
    assert response.status_code == 200

    verify = client.get("/api/auth/verify")
    user = verify.json()["user"]
    assert user["role"] == "read_only"
    assert user["is_superuser"] is False


def test_demo_user_denied_secrets_admin_route(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AEGISNEX_DEMO_ENABLED", "true")
    monkeypatch.setenv("AEGISNEX_DEMO_PASSWORD", "demo-secret-not-a-real-password")
    app = make_app(tmp_path)
    client = TestClient(app, base_url="https://testserver")
    client.post("/api/auth/demo-login")

    response = client.post("/api/secrets", json={"name": "x", "value": "y"})

    assert response.status_code == 403


def test_demo_user_denied_docker_mutation_route(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AEGISNEX_DEMO_ENABLED", "true")
    monkeypatch.setenv("AEGISNEX_DEMO_PASSWORD", "demo-secret-not-a-real-password")
    app = make_app(tmp_path)
    client = TestClient(app, base_url="https://testserver")
    client.post("/api/auth/demo-login")

    response = client.post("/api/containers/some-container/start")

    assert response.status_code == 403


def test_demo_login_works_under_production_tenant_enforcement(tmp_path: Path, monkeypatch) -> None:
    # The demo account is freshly seeded and non-superuser, so production's
    # tenant-membership requirement must not lock it out (see
    # test_production_requires_org_membership_for_non_admin_user for the
    # general case this would otherwise hit).
    monkeypatch.setenv("AEGISNEX_ENV", "production")
    monkeypatch.setenv("AEGISNEX_REQUIRE_TENANT_MEMBERSHIP", "true")
    enable_oidc_env(monkeypatch)
    monkeypatch.setenv("AEGISNEX_DEMO_ENABLED", "true")
    monkeypatch.setenv("AEGISNEX_DEMO_PASSWORD", "demo-secret-not-a-real-password")
    auth_manager = AuthManager(
        user_store=UserStore(tmp_path / "users.db"),
        jwt_secret="test-secret-32chars-long-please!",
    )
    # TenantManager needs a real PlatformRepository (placeholder/_execute/
    # _fetch_all support); the lightweight FakeRepository used elsewhere in
    # this suite doesn't implement that surface.
    real_repo = PlatformRepository(f"sqlite:///{tmp_path / 'platform.db'}")
    real_repo.initialize()
    services = build_services(tmp_path)
    services.platform_repository = real_repo
    app = create_app(
        services=services,
        auth_manager=auth_manager,
        telemetry_db_path=str(tmp_path / "telemetry.db"),
    )
    client = TestClient(app, base_url="https://testserver")

    login_response = client.post("/api/auth/demo-login")
    assert login_response.status_code == 200

    verify = client.get("/api/auth/verify")
    assert verify.status_code == 200
    assert verify.json()["user"]["role"] == "read_only"


def test_normal_admin_login_still_works_after_demo_changes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AEGISNEX_SEED_DEFAULT_ADMIN", "true")
    monkeypatch.setenv("AEGISNEX_BOOTSTRAP_ADMIN_PASSWORD", "admin-secret-not-a-real-password")
    app = make_app(tmp_path)
    client = TestClient(app, base_url="https://testserver")

    response = client.post(
        "/api/login",
        data={"username": "admin", "password": "admin-secret-not-a-real-password"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]

    verify = client.get("/api/auth/verify")
    user = verify.json()["user"]
    assert user["role"] == "administrator"
    assert user["is_superuser"] is True
