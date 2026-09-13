import base64
import importlib.util
import sys
from pathlib import Path

from cryptography.fernet import Fernet


def _load_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "generate_secrets.py"
    spec = importlib.util.spec_from_file_location("generate_secrets", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


generate_secrets = _load_module()


def test_jwt_secret_is_32_bytes_hex() -> None:
    value = generate_secrets.generate_jwt_secret()
    assert len(value.encode("utf-8")) >= 32
    bytes.fromhex(value)  # raises ValueError if not valid hex


def test_demo_password_has_high_entropy() -> None:
    value = generate_secrets.generate_demo_password()
    assert len(value) >= 16


def test_secret_key_is_valid_fernet_key() -> None:
    value = generate_secrets.generate_secret_key()
    raw = base64.urlsafe_b64decode(value.encode("ascii"))
    assert len(raw) == 32
    fernet = Fernet(value.encode("ascii"))
    token = fernet.encrypt(b"roundtrip")
    assert fernet.decrypt(token) == b"roundtrip"


def test_values_are_random_each_call() -> None:
    assert generate_secrets.generate_jwt_secret() != generate_secrets.generate_jwt_secret()
    assert generate_secrets.generate_demo_password() != generate_secrets.generate_demo_password()
    assert generate_secrets.generate_secret_key() != generate_secrets.generate_secret_key()


def test_main_prints_only_no_file_writes(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    generate_secrets.main()
    captured = capsys.readouterr()
    assert "AEGISNEX_JWT_SECRET=" in captured.out
    assert "AEGISNEX_DEMO_PASSWORD=" in captured.out
    assert "AEGISNEX_SECRET_KEY=" in captured.out
    assert list(tmp_path.iterdir()) == []
