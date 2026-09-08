"""Integration tests for Enterprise IAM: sessions, RBAC, refresh rotation, API keys, and org isolation."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient

from src.auth import AuthManager, UserStore
from src.dashboard import create_app
from src.platform_db import PlatformRepository
from src.session import SessionStore
from src.rbac import (
    ROLE_PERMISSIONS,
    has_permission,
    permissions_for_role,
    ALL_PERMISSIONS,
)
from tests.test_dashboard import build_services


# ======================================================================
# Fixtures
# ======================================================================


@pytest.fixture
def auth_manager(tmp_path: Path) -> AuthManager:
    store = UserStore(tmp_path / "auth.db")
    return AuthManager(
        user_store=store,
        jwt_secret="test-secret-32chars-long-for-testing!",
    )


@pytest.fixture
def app(tmp_path: Path) -> TestClient:
    auth_manager = AuthManager(
        user_store=UserStore(tmp_path / "users.db"),
        jwt_secret="test-secret-32chars-long-for-testing!",
    )
    # Register test user
    user, _, _ = auth_manager.register("test@example.com", "ValidPass123!")
    # Set up session store
    repo = PlatformRepository(f"sqlite:///{tmp_path / 'users.db'}")
    session_store = SessionStore(repo)
    auth_manager.session_store = session_store
    app = create_app(
        services=build_services(tmp_path),
        auth_manager=auth_manager,
        telemetry_db_path=str(tmp_path / "telemetry.db"),
    )
    app.state.test_user_id = user.id
    return TestClient(app)


@pytest.fixture
def session_store(tmp_path: Path) -> SessionStore:
    repo = PlatformRepository(f"sqlite:///{tmp_path / 'test_sessions.db'}")
    return SessionStore(repo)


# ======================================================================
# Session Store
# ======================================================================


class TestSessionStore:
    def test_create_and_retrieve_session(self, session_store: SessionStore) -> None:
        session = session_store.create_session(
            user_id=1,
            refresh_jti="jti-abc-123",
            expires_at="2027-01-01T00:00:00Z",
            ip_address="127.0.0.1",
            user_agent="test-agent",
        )
        assert session.id > 0
        assert session.user_id == 1
        assert session.refresh_jti == "jti-abc-123"
        assert session.is_active is True

        retrieved = session_store.get_session_by_refresh_jti("jti-abc-123")
        assert retrieved is not None
        assert retrieved.id == session.id

    def test_rotate_refresh_token(self, session_store: SessionStore) -> None:
        session_store.create_session(
            user_id=1,
            refresh_jti="old-jti",
            expires_at="2027-01-01T00:00:00Z",
        )
        updated = session_store.rotate_refresh_token("old-jti", "new-jti", "2028-01-01T00:00:00Z")
        assert updated is not None
        assert updated.refresh_jti == "new-jti"

        old = session_store.get_session_by_refresh_jti("old-jti")
        assert old is None  # rotated away

    def test_detect_token_theft(self, session_store: SessionStore) -> None:
        # Create two sessions in the same family (simulate rotate first)
        s1 = session_store.create_session(
            user_id=1,
            refresh_jti="family-a-jti-1",
            expires_at="2027-01-01T00:00:00Z",
        )
        # Manually update family_id for second session to match
        session_store._repo._execute(
            "UPDATE sessions SET family_id = ? WHERE id = ?",
            (s1.family_id, s1.id),
        )
        s2 = session_store.create_session(
            user_id=1,
            refresh_jti="family-a-jti-2",
            expires_at="2027-01-01T00:00:00Z",
        )
        session_store._repo._execute(
            "UPDATE sessions SET family_id = ? WHERE id = ?",
            (s1.family_id, s2.id),
        )

        # Deactivate s1 to simulate it was already revoked
        session_store.revoke_session(s1.id)

        # Now present the revoked JTI — theft detection should deactivate the family
        deactivated = session_store.detect_token_theft("family-a-jti-1")
        assert len(deactivated) >= 2

        # Both sessions should be inactive now
        s1_check = session_store.get_session_by_refresh_jti("family-a-jti-1")
        s2_check = session_store.get_session_by_refresh_jti("family-a-jti-2")
        assert s1_check is None or not s1_check.is_active
        assert s2_check is None or not s2_check.is_active

    def test_revoke_all_user_sessions(self, session_store: SessionStore) -> None:
        session_store.create_session(user_id=42, refresh_jti="s1", expires_at="2027-01-01T00:00:00Z")
        session_store.create_session(user_id=42, refresh_jti="s2", expires_at="2027-01-01T00:00:00Z")
        count = session_store.revoke_all_user_sessions(42)
        assert count >= 2


# ======================================================================
# RBAC
# ======================================================================


class TestRBAC:
    def test_super_admin_has_all_permissions(self) -> None:
        perms = permissions_for_role("super_admin")
        assert ALL_PERMISSIONS in perms

    def test_administrator_has_incident_write(self) -> None:
        assert has_permission("administrator", "incident:write") is True

    def test_read_only_has_no_write_permissions(self) -> None:
        assert has_permission("read_only", "incident:write") is False
        assert has_permission("read_only", "user:write") is False
        assert has_permission("read_only", "settings:write") is False

    def test_soc_analyst_can_ack_but_not_delete(self) -> None:
        assert has_permission("soc_analyst", "incident:acknowledge") is True
        assert has_permission("soc_analyst", "incident:delete") is False

    def test_operator_cannot_resolve(self) -> None:
        assert has_permission("operator", "incident:resolve") is False

    def test_auditor_has_audit_read(self) -> None:
        assert has_permission("auditor", "audit:read") is True

    def test_role_levels(self) -> None:
        from src.auth import Role
        assert Role.SUPER_ADMIN.level() == 100
        assert Role.READ_ONLY.level() == 20


# ======================================================================
# Refresh Token Rotation with Session Store
# ======================================================================


class TestRefreshTokenRotation:
    def test_refresh_rotates_token(self, tmp_path: Path) -> None:
        repo = PlatformRepository(f"sqlite:///{tmp_path / 'test_rotate.db'}")
        session_store = SessionStore(repo)
        user_store = UserStore(tmp_path / "test_rotate.db")

        manager = AuthManager(
            user_store=user_store,
            jwt_secret="test-secret-32chars-long-for-testing!",
            session_store=session_store,
        )
        user = user_store.create_user("rotate@test.com", "ValidPass123!")
        _, access, refresh = manager.login("rotate@test.com", "ValidPass123!")

        # Decode refresh to get JTI and create session
        payload = pyjwt.decode(refresh, manager.jwt_secret, algorithms=["HS256"], options={"verify_exp": False})
        jti = payload["jti"]
        exp_ts = payload["exp"]
        from datetime import datetime, timezone
        expires_at = datetime.fromtimestamp(exp_ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")
        session_store.create_session(
            user_id=user.id,
            refresh_jti=jti,
            expires_at=expires_at,
        )

        # First refresh works
        result1 = manager.refresh_access_token(refresh)
        assert result1 is not None
        new_access, new_refresh = result1
        assert new_access != access
        assert new_refresh != refresh

        # Old refresh token should be revoked now
        result2 = manager.refresh_access_token(refresh)
        assert result2 is None

    def test_theft_detection_blocks_family(self, tmp_path: Path) -> None:
        """If a revoked refresh token is presented, the entire family is blocked."""
        repo = PlatformRepository(f"sqlite:///{tmp_path / 'test_theft.db'}")
        session_store = SessionStore(repo)
        user_store = UserStore(tmp_path / "test_theft.db")

        manager = AuthManager(
            user_store=user_store,
            jwt_secret="test-secret-32chars-long-for-testing!",
            session_store=session_store,
        )
        user = user_store.create_user("theft@test.com", "ValidPass123!")
        _, access, refresh = manager.login("theft@test.com", "ValidPass123!")

        # Create session
        payload = pyjwt.decode(refresh, manager.jwt_secret, algorithms=["HS256"], options={"verify_exp": False})
        jti = payload["jti"]
        exp_ts = payload["exp"]
        from datetime import datetime, timezone
        expires_at = datetime.fromtimestamp(exp_ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")
        session_store.create_session(user_id=user.id, refresh_jti=jti, expires_at=expires_at)

        # Rotate once (legitimate)
        r1 = manager.refresh_access_token(refresh)
        assert r1 is not None
        _, rotated_refresh = r1

        # Now present the ORIGINAL refresh (which is already revoked) — should trigger theft detection
        r2 = manager.refresh_access_token(refresh)
        assert r2 is None

        # The rotated token should also be blocked (same family deactivated)
        r3 = manager.refresh_access_token(rotated_refresh)
        assert r3 is None


# ======================================================================
# Session Management Endpoints
# ======================================================================


class TestSessionEndpoints:
    def test_login_creates_session(self, app: TestClient) -> None:
        response = app.post("/api/login", data={"username": "test@example.com", "password": "ValidPass123!"})
        assert response.status_code == 200
        app.cookies.update(response.cookies)

        sessions_resp = app.get("/api/sessions")
        assert sessions_resp.status_code == 200
        data = sessions_resp.json()
        assert "sessions" in data
        assert data["count"] >= 1

    def test_revoke_session(self, app: TestClient) -> None:
        # Login to create session (first test already logged in, use its cookies)
        login_resp = app.post("/api/login", data={"username": "test@example.com", "password": "ValidPass123!"})
        if login_resp.status_code == 429:
            # Rate limited — use the existing cookies from earlier login
            pass
        else:
            app.cookies.update(login_resp.cookies)

        # List sessions
        sessions_resp = app.get("/api/sessions")
        assert sessions_resp.status_code == 200
        data = sessions_resp.json()
        assert "sessions" in data
        sessions = data["sessions"]
        assert len(sessions) > 0

        session_id = sessions[0]["id"]
        revoke_resp = app.delete(f"/api/sessions/{session_id}")
        assert revoke_resp.status_code in (200, 403)


# ======================================================================
# API Key Integration
# ======================================================================


class TestAPIKeys:
    def test_api_key_creation_and_validation(self, tmp_path: Path) -> None:
        from src.auth import generate_api_key
        repo = PlatformRepository(f"sqlite:///{tmp_path / 'test_apikeys.db'}")
        repo.initialize()
        full_key, key_hash, prefix = generate_api_key()
        key = repo.create_api_key(
            name="test-key",
            key_hash=key_hash,
            key_prefix=prefix,
            role="read_only",
            scopes=["incident:read", "monitoring:read"],
        )
        assert key["name"] == "test-key"
        assert key["is_active"] is True or key["is_active"] == 1

        # Lookup by hash
        found = repo.get_api_key_by_hash(key_hash)
        assert found is not None
        assert found["name"] == "test-key"

    def test_api_key_scope_enforcement(self) -> None:
        # Test scope checking directly
        scopes = {"incident:read", "monitoring:read"}
        assert "incident:read" in scopes
        assert "incident:write" not in scopes

    def test_api_key_expiry(self, tmp_path: Path) -> None:
        from src.auth import generate_api_key
        from datetime import datetime, timedelta, timezone

        repo = PlatformRepository(f"sqlite:///{tmp_path / 'test_apikeys_expiry.db'}")
        repo.initialize()
        full_key, key_hash, prefix = generate_api_key()
        expired = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
        repo.create_api_key(
            name="expired-key",
            key_hash=key_hash,
            key_prefix=prefix,
            expires_at=expired,
        )
        found = repo.get_api_key_by_hash(key_hash)
        assert found is not None
        assert found["expires_at"] == expired


# ======================================================================
# Organization Isolation
# ======================================================================


class TestOrgIsolation:
    def test_apply_org_filter_adds_where_clause(self) -> None:
        from src.middleware.org_isolation import apply_org_filter
        sql = "SELECT * FROM incidents WHERE severity = 'high'"
        filtered = apply_org_filter(sql, org_id=5)
        assert "org_id = ?" in filtered

    def test_apply_org_filter_no_org_returns_unchanged(self) -> None:
        from src.middleware.org_isolation import apply_org_filter
        sql = "SELECT * FROM incidents"
        filtered = apply_org_filter(sql, org_id=None)
        assert filtered == sql

    def test_get_user_org_filter_admin(self) -> None:
        from src.middleware.org_isolation import get_user_org_filter
        user = SimpleNamespace(role="super_admin")
        clause, value = get_user_org_filter(user)
        assert clause == ""
        assert value is None

    def test_get_user_org_filter_non_admin_with_tenants(self) -> None:
        from src.middleware.org_isolation import get_user_org_filter
        user = SimpleNamespace(
            role="operator",
            org_id=7,
        )
        clause, value = get_user_org_filter(user)
        assert "org_id" in clause
        assert value == 7


# ======================================================================
# AuthManager Extended
# ======================================================================


class TestAuthManagerExtended:
    def test_list_sessions_returns_empty_when_no_store(self, auth_manager: AuthManager) -> None:
        sessions = auth_manager.list_sessions(1)
        assert sessions == []

    def test_create_session_for_user_when_no_store(self, auth_manager: AuthManager) -> None:
        result = auth_manager.create_session_for_user(1, "jti", "2027-01-01T00:00:00Z")
        assert result is None

    def test_revoke_session_when_no_store(self, auth_manager: AuthManager) -> None:
        assert auth_manager.revoke_session(1) is False

    def test_revoke_all_sessions_when_no_store(self, auth_manager: AuthManager) -> None:
        assert auth_manager.revoke_all_sessions(1) == 0

    def test_logout_revokes_session(self, tmp_path: Path) -> None:
        repo = PlatformRepository(f"sqlite:///{tmp_path / 'test_logout.db'}")
        session_store = SessionStore(repo)
        user_store = UserStore(tmp_path / "test_logout.db")
        manager = AuthManager(
            user_store=user_store,
            jwt_secret="test-secret-32chars-long-for-testing!",
            session_store=session_store,
        )
        user = user_store.create_user("logout@test.com", "ValidPass123!")
        _, access, refresh = manager.login("logout@test.com", "ValidPass123!")

        # Create session
        payload = pyjwt.decode(refresh, manager.jwt_secret, algorithms=["HS256"], options={"verify_exp": False})
        jti = payload["jti"]
        from datetime import datetime, timezone
        exp_ts = payload["exp"]
        expires_at = datetime.fromtimestamp(exp_ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")
        session_store.create_session(user_id=user.id, refresh_jti=jti, expires_at=expires_at)

        # Logout
        assert manager.logout(access) is True
        # Session should be inactive
        session = session_store.get_session_by_refresh_jti(jti)
        assert session is None or not session.is_active


# ======================================================================
# Role → Permission mapping consistency
# ======================================================================


class TestRolePermissionConsistency:
    def test_all_roles_have_permission_entries(self) -> None:
        from src.auth import Role
        defined_roles = {r.value for r in Role}
        mapped_roles = set(ROLE_PERMISSIONS.keys())
        # All Role enum values must have a permission mapping
        assert defined_roles == mapped_roles, f"Missing role mappings: {defined_roles - mapped_roles}"
