from pathlib import Path

from src.auth import AuthManager, UserStore, hash_password, verify_password


def test_password_hashing_verifies_and_does_not_store_plaintext() -> None:
    hashed = hash_password("correct-password")

    assert "correct-password" not in hashed
    assert verify_password("correct-password", hashed) is True
    assert verify_password("wrong-password", hashed) is False


def test_user_store_creates_and_authenticates_user(tmp_path: Path) -> None:
    store = UserStore(tmp_path / "users.db")

    user = store.create_user("Admin@Example.com", "password123")

    assert user.email == "admin@example.com"
    assert user.hashed_password.startswith("pbkdf2_sha256$")
    assert store.authenticate("admin@example.com", "password123") == user
    assert store.authenticate("admin@example.com", "bad-password") is None


def test_auth_manager_issues_and_reads_jwt(tmp_path: Path) -> None:
    manager = AuthManager(
        user_store=UserStore(tmp_path / "users.db"),
        jwt_secret="test-secret",
    )

    user, token, refresh = manager.register("ops@example.com", "password123")
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
    manager.register("ops@example.com", "password123")

    assert manager.login("ops@example.com", "wrong-password") is None


def test_auth_manager_logout_revokes_token(tmp_path: Path) -> None:
    manager = AuthManager(
        user_store=UserStore(tmp_path / "users.db"),
        jwt_secret="test-secret",
    )
    user, token, refresh = manager.register("ops@example.com", "password123")

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
    user, token, _ = AuthManager(store, jwt_secret="test-secret").register("viewer@example.com", "password123")

    with store._connect() as connection:
        connection.execute("UPDATE users SET role = 'viewer' WHERE id = ?", (user.id,))

    refreshed = store.get_user_by_id(user.id)
    assert refreshed is not None
    assert refreshed.role == "read_only"
