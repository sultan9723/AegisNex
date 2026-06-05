from pathlib import Path

from src.auth import AuthManager, UserStore, decode_jwt, hash_password, verify_password


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

    user, token = manager.register("ops@example.com", "password123")
    payload = decode_jwt(token, "test-secret")

    assert payload is not None
    assert payload["sub"] == str(user.id)
    assert manager.get_user_from_token(token) == user
    assert manager.get_user_from_token(token + "tampered") is None


def test_auth_manager_login_returns_none_for_invalid_credentials(tmp_path: Path) -> None:
    manager = AuthManager(
        user_store=UserStore(tmp_path / "users.db"),
        jwt_secret="test-secret",
    )
    manager.register("ops@example.com", "password123")

    assert manager.login("ops@example.com", "wrong-password") is None
