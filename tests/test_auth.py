from pathlib import Path

import pytest

from src.auth import AuthError, AuthManager, TokenBlacklist, UserStore, hash_password, verify_password
from src.platform_db import PlatformRepository


def test_password_hashing_verifies_and_does_not_store_plaintext() -> None:
    hashed = hash_password("correct-password")

    assert "correct-password" not in hashed
    assert verify_password("correct-password", hashed) is True
    assert verify_password("wrong-password", hashed) is False


def test_user_store_creates_and_authenticates_user(tmp_path: Path) -> None:
    store = UserStore(tmp_path / "users.db")

    user = store.create_user("Admin@Example.com", "password12345")

    assert user.email == "admin@example.com"
    assert user.hashed_password.startswith("pbkdf2_sha256$")
    assert store.authenticate("admin@example.com", "password12345") == user
    assert store.authenticate("admin@example.com", "bad-password") is None


def test_auth_manager_issues_and_reads_jwt(tmp_path: Path) -> None:
    manager = AuthManager(
        user_store=UserStore(tmp_path / "users.db"),
        jwt_secret="test-secret",
    )

    user, token, refresh = manager.register("ops@example.com", "password12345")
    decoded = manager.get_user_from_token(token)

    assert decoded is not None
    assert decoded.id == user.id
    assert decoded.email == user.email
    assert manager.get_user_from_token(token) == user
    assert manager.get_user_from_token(token + "tampered") is None
    assert manager.get_user_from_token("invalid-token-here") is None


def test_auth_manager_login_returns_none_for_invalid_credentials(tmp_path: Path) -> None:
    manager = AuthManager(
        user_store=UserStore(tmp_path / "users.db"),
        jwt_secret="test-secret",
    )
    manager.register("ops@example.com", "password12345")

    assert manager.login("ops@example.com", "wrong-password") is None


def test_auth_manager_logout_revokes_token(tmp_path: Path) -> None:
    manager = AuthManager(
        user_store=UserStore(tmp_path / "users.db"),
        jwt_secret="test-secret",
    )
    user, token, refresh = manager.register("ops@example.com", "password12345")

    assert manager.get_user_from_token(token) is not None
    assert manager.logout(token) is True
    assert manager.get_user_from_token(token) is None


def test_auth_manager_hardcoded_secret_raises_error(tmp_path: Path) -> None:
    """AuthManager must raise RuntimeError if no JWT secret is provided and env var is unset."""
    import os
    # Temporarily unset the env var to test the error
    saved = os.environ.pop("AEGISNEX_JWT_SECRET", None)
    try:
        import src.auth as auth_mod
        # Reload to clear cached env
        from unittest.mock import patch
        with patch.dict(os.environ, {}, clear=True):
            try:
                AuthManager(
                    user_store=UserStore(tmp_path / "users.db"),
                    jwt_secret=None,
                )
                assert False, "Should have raised RuntimeError"
            except RuntimeError:
                pass  # Expected
    finally:
        if saved is not None:
            os.environ["AEGISNEX_JWT_SECRET"] = saved


def test_auth_manager_normalizes_legacy_viewer_role_on_read(tmp_path: Path) -> None:
    store = UserStore(tmp_path / "users.db")
    user, token, _ = AuthManager(store, jwt_secret="test-secret").register("viewer@example.com", "password12345")

    with store._connect() as connection:
        connection.execute("UPDATE users SET role = 'viewer' WHERE id = ?", (user.id,))

    refreshed = store.get_user_by_id(user.id)
    assert refreshed is not None
    assert refreshed.role == "read_only"


def test_external_login_provisions_verified_user_and_links_identity(tmp_path: Path) -> None:
    store = UserStore(tmp_path / "users.db")
    manager = AuthManager(store, jwt_secret="test-secret")

    user, access_token, refresh_token = manager.external_login(
        provider="https://login.example.com",
        subject="subject-123",
        email="Ops@Example.com",
        display_name="Ops Lead",
        role="operator",
        claims={"email": "Ops@Example.com", "sub": "subject-123"},
    )

    assert user.email == "ops@example.com"
    assert user.display_name == "Ops Lead"
    assert user.role == "operator"
    assert user.is_verified is True
    assert manager.get_user_from_token(access_token) == user
    assert manager.refresh_session(refresh_token) is not None


def test_external_login_reuses_existing_identity(tmp_path: Path) -> None:
    store = UserStore(tmp_path / "users.db")
    manager = AuthManager(store, jwt_secret="test-secret")

    first, _, _ = manager.external_login(
        provider="https://login.example.com",
        subject="subject-123",
        email="ops@example.com",
        display_name="Ops",
    )
    second, _, _ = manager.external_login(
        provider="https://login.example.com",
        subject="subject-123",
        email="ops@example.com",
        display_name="Ops Updated",
    )

    assert second.id == first.id
    assert store.get_user_by_email("ops@example.com") is not None


# --- UserStore.seed_demo_user ---
# (called by POST /api/auth/demo-login the first time a demo session is
# requested - see tests/test_demo_login.py for the HTTP-level behavior)


def test_seed_demo_user_creates_restricted_read_only_account(tmp_path: Path) -> None:
    store = UserStore(tmp_path / "users.db")

    store.seed_demo_user("demo", "demo-secret-not-a-real-password")

    user = store.get_user_by_email("demo")
    assert user is not None
    assert user.role == "read_only"
    assert user.is_superuser is False
    assert store.authenticate("demo", "demo-secret-not-a-real-password") == user


def test_seed_demo_user_requires_password(tmp_path: Path) -> None:
    store = UserStore(tmp_path / "users.db")

    with pytest.raises(AuthError):
        store.seed_demo_user("demo", "")

    assert store.get_user_by_email("demo") is None


def test_seed_demo_user_resyncs_password_when_rotated(tmp_path: Path) -> None:
    store = UserStore(tmp_path / "users.db")
    store.seed_demo_user("demo", "old-demo-password")

    store.seed_demo_user("demo", "new-demo-password")

    assert store.authenticate("demo", "old-demo-password") is None
    assert store.authenticate("demo", "new-demo-password") is not None


def test_seed_demo_user_survives_concurrent_insert_race(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two concurrent first-time demo-login requests can both see "no
    existing user" and both attempt the INSERT; the one that loses the race
    must reconcile against the winner's row instead of raising and turning
    into an unhandled 500 in the demo-login route."""
    store = UserStore(tmp_path / "users.db")

    original_get_user_by_email = store.get_user_by_email
    calls = {"count": 0}

    def racy_get_user_by_email(email: str):
        calls["count"] += 1
        if calls["count"] == 1:
            # Simulate the TOCTOU window: report "no user yet" even though a
            # concurrent request is about to (or already did) insert one.
            connection = store._connect()
            with connection:
                connection.execute(
                    "INSERT INTO users (email, hashed_password, is_active, is_superuser, "
                    "is_verified, role, created_at) VALUES (?, ?, 1, 0, 1, 'read_only', ?)",
                    (email.lower(), hash_password("winner-password"), "2026-01-01T00:00:00Z"),
                )
            return None
        return original_get_user_by_email(email)

    monkeypatch.setattr(store, "get_user_by_email", racy_get_user_by_email)

    store.seed_demo_user("demo", "loser-password")

    user = store.get_user_by_email("demo")
    assert user is not None
    assert user.role == "read_only"
    assert user.is_superuser is False


# --- PlatformRepository-backed UserStore / TokenBlacklist / AuthManager ---
#
# Production (Docker behind Cloudflare Tunnel, Neon PostgreSQL) wires
# AuthManager(repository=platform_repository) so users/tokens are persisted
# in Postgres instead of a local SQLite file that would not survive a
# container restart. These tests exercise that same repository-backed code
# path against a real (SQLite-backed) PlatformRepository - the SQL is
# parameterized through repo.placeholder/_execute/_fetch_all exactly the
# way it would run against PostgreSQL, so this is a high-fidelity stand-in
# without requiring a live Postgres server.


def _repo(tmp_path: Path) -> PlatformRepository:
    repo = PlatformRepository(f"sqlite:///{tmp_path / 'platform.db'}")
    repo.initialize()
    return repo


def test_repo_backed_user_store_create_and_authenticate(tmp_path: Path) -> None:
    store = UserStore(repository=_repo(tmp_path))

    user = store.create_user("ops@example.com", "password12345", role="operator")

    assert user.email == "ops@example.com"
    assert user.role == "operator"
    assert store.get_user_by_id(user.id) == user
    assert store.authenticate("ops@example.com", "password12345") == user
    assert store.authenticate("ops@example.com", "wrong-password") is None


def test_repo_backed_user_store_rejects_duplicate_email(tmp_path: Path) -> None:
    store = UserStore(repository=_repo(tmp_path))
    store.create_user("ops@example.com", "password12345")

    with pytest.raises(AuthError):
        store.create_user("ops@example.com", "password12345")


def test_repo_backed_user_store_update_methods(tmp_path: Path) -> None:
    store = UserStore(repository=_repo(tmp_path))
    user = store.create_user("ops@example.com", "password12345")

    assert store.update_role(user.id, "read_only") is True
    assert store.get_user_by_id(user.id).role == "read_only"

    assert store.update_password(user.id, "new-password123") is True
    assert store.authenticate("ops@example.com", "new-password123") is not None

    assert store.update_display_name(user.id, "Ops Lead") is True
    assert store.get_user_by_id(user.id).display_name == "Ops Lead"

    store.update_last_login(user.id)
    assert store.get_user_by_id(user.id).last_login is not None

    assert store.set_verified(user.id, True) is True
    assert store.get_user_by_id(user.id).is_verified is True

    assert store.deactivate_user(user.id) is True
    assert store.authenticate("ops@example.com", "new-password123") is None

    # Updating a nonexistent user is a well-defined no-op, not an error.
    assert store.update_role(999999, "operator") is False


def test_repo_backed_seed_demo_user_stays_restricted(tmp_path: Path) -> None:
    store = UserStore(repository=_repo(tmp_path))

    store.seed_demo_user("demo", "demo-secret-not-a-real-password")
    demo = store.get_user_by_email("demo")

    assert demo is not None
    assert demo.role == "read_only"
    assert demo.is_superuser is False

    # Re-seeding with a rotated password reconciles the existing account
    # instead of erroring, and stays restricted.
    store.seed_demo_user("demo", "rotated-secret-not-a-real-password")
    demo = store.get_user_by_email("demo")
    assert demo.role == "read_only"
    assert demo.is_superuser is False
    assert store.authenticate("demo", "rotated-secret-not-a-real-password") is not None


def test_repo_backed_seed_default_admin(tmp_path: Path) -> None:
    store = UserStore(repository=_repo(tmp_path))

    store.seed_default_admin("admin-secret-not-a-real-password")
    admin = store.get_user_by_email("admin")

    assert admin is not None
    assert admin.role == "administrator"
    assert admin.is_superuser is True


def test_repo_backed_upsert_external_user_new_and_repeat_login(tmp_path: Path) -> None:
    store = UserStore(repository=_repo(tmp_path))

    first = store.upsert_external_user(
        provider="https://idp.example.com",
        subject="subject-1",
        email="sso@example.com",
        display_name="SSO User",
        role="soc_analyst",
    )
    assert first.email == "sso@example.com"
    assert first.role == "soc_analyst"
    assert first.is_verified is True

    second = store.upsert_external_user(
        provider="https://idp.example.com",
        subject="subject-1",
        email="sso@example.com",
        display_name="SSO User Renamed",
    )
    assert second.id == first.id


def test_repo_backed_token_blacklist_persists_across_instances(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    blacklist = TokenBlacklist(repository=repo)

    assert blacklist.is_revoked("jti-1") is False
    blacklist.revoke("jti-1", 9999999999)
    assert blacklist.is_revoked("jti-1") is True

    # A second instance against the same repository must see the same
    # revocation on load (this is what makes it durable across restarts).
    reloaded = TokenBlacklist(repository=repo)
    assert reloaded.is_revoked("jti-1") is True


def test_repo_backed_token_blacklist_revoke_all_for_user_uses_wide_sentinel(
    tmp_path: Path,
) -> None:
    """Regression guard: the "revoked forever" sentinel (9999999999) must fit
    the token_blacklist.expires_at column. A 32-bit PostgreSQL INTEGER would
    overflow on this value - see alembic/versions/d4f8a2c9e6b3_*.py, which
    widens it to BIGINT. SQLite has no such limit, so this exercises the
    code path and value without needing a live PostgreSQL server."""
    repo = _repo(tmp_path)
    blacklist = TokenBlacklist(repository=repo)

    blacklist.revoke_all_for_user(42, auth_manager=None)

    assert blacklist.is_revoked("user_revoke_42") is True
    rows = repo._fetch_all(
        f"SELECT expires_at FROM token_blacklist WHERE jti = {repo.placeholder}",
        ("user_revoke_42",),
    )
    assert rows[0]["expires_at"] == 9999999999


def test_auth_manager_uses_repository_backed_store_when_given(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    manager = AuthManager(repository=repo, jwt_secret="test-secret-32chars-long-please!")

    assert manager.user_store._repo is repo
    assert manager.blacklist._repo is repo

    user, access_token, refresh_token = manager.register("ops@example.com", "password12345")
    assert manager.get_user_from_token(access_token) == user

    # The same data must be visible from a second AuthManager sharing the
    # same repository - i.e. it survived "restart" (a fresh process
    # reattaching to the same database), which is the entire point of this
    # migration away from a local SQLite file.
    manager2 = AuthManager(repository=repo, jwt_secret="test-secret-32chars-long-please!")
    assert manager2.user_store.get_user_by_email("ops@example.com") is not None
