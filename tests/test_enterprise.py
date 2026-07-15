"""Tests for Sprint G — Enterprise Platform features."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from src.auth import Role, User, UserStore, AuthManager
from src.platform_db import PlatformRepository
from src.secrets import SecretManager
from src.backup import BackupManager


@pytest.fixture(autouse=True)
def _set_secret_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure AEGISNEX_SECRET_KEY is set for every test in this module."""
    monkeypatch.setenv("AEGISNEX_SECRET_KEY", "BjEwcBgtq1O9dWPmKX6HRlEdfdiTgx4O15jOqoDRCSk=")


# =========================================================================
# Enhanced RBAC
# =========================================================================

def test_role_enum_has_six_values() -> None:
    values = {r.value for r in Role}
    assert values == {"super_admin", "administrator", "soc_analyst", "operator", "read_only", "auditor"}


def test_role_level_ordering() -> None:
    assert Role.SUPER_ADMIN.level() == 100
    assert Role.ADMINISTRATOR.level() == 80
    assert Role.SOC_ANALYST.level() == 60
    assert Role.OPERATOR.level() == 40
    assert Role.READ_ONLY.level() == 20
    assert Role.AUDITOR.level() == 10


def test_role_from_str_maps_legacy_aliases() -> None:
    assert Role.from_str("admin") == Role.ADMINISTRATOR
    assert Role.from_str("viewer") == Role.READ_ONLY
    assert Role.from_str("administrator") == Role.ADMINISTRATOR
    assert Role.from_str("read_only") == Role.READ_ONLY


def test_role_requires_level() -> None:
    admins = Role.requires_level("administrator")
    assert "super_admin" in admins
    assert "administrator" in admins
    assert "soc_analyst" not in admins


def test_user_model_new_role(tmp_path: Path) -> None:
    store = UserStore(tmp_path / "test_roles.db")
    user = store.create_user("soc@example.com", "password123", role="soc_analyst")
    assert user.role == "soc_analyst"
    assert user.display_role == "SOC Analyst"
    assert user.display_name == ""
    assert user.last_login is None
    assert user.mfa_enabled is False


def test_user_has_minimum_role(tmp_path: Path) -> None:
    store = UserStore(tmp_path / "test_min_role.db")
    admin = store.create_user("admin@example.com", "password123", role="administrator")
    assert admin.has_minimum_role("operator") is True
    assert admin.has_minimum_role("super_admin") is False

    viewer = store.create_user("viewer@example.com", "password123", role="read_only")
    assert viewer.has_minimum_role("read_only") is True
    assert viewer.has_minimum_role("operator") is False


def test_user_store_creates_all_new_roles(tmp_path: Path) -> None:
    store = UserStore(tmp_path / "test_all_roles.db")
    for role_name in ("super_admin", "administrator", "soc_analyst", "operator", "read_only", "auditor"):
        user = store.create_user(f"{role_name}@example.com", "password123", role=role_name)
        assert user.role == role_name


def test_auth_manager_login_records_last_login(tmp_path: Path) -> None:
    manager = AuthManager(
        user_store=UserStore(tmp_path / "test_last_login.db"),
        jwt_secret="test-secret-for-testing",
    )
    user, _, _ = manager.register("login@example.com", "password123")
    result = manager.login("login@example.com", "password123")
    assert result is not None
    assert result[0].last_login is not None


# =========================================================================
# Secret Management
# =========================================================================

def test_secret_manager_encrypt_decrypt_roundtrip() -> None:
    mgr = SecretManager()
    plaintext = "s3cret-value!"
    encrypted = mgr.encrypt(plaintext)
    assert encrypted != plaintext
    decrypted = mgr.decrypt(encrypted)
    assert decrypted == plaintext


def test_secret_manager_store_and_retrieve(tmp_path: Path) -> None:
    repo = PlatformRepository(f"sqlite:///{tmp_path / 'secrets.db'}")
    mgr = SecretManager(repo=repo)
    mgr.store_secret("smtp_password", "smtp-secret-123", category="smtp")
    mgr.store_secret("slack_token", "xoxb-token-abc", category="slack")
    secrets = mgr.list_secrets()
    assert len(secrets) == 2
    names = {s["name"] for s in secrets}
    assert names == {"smtp_password", "slack_token"}
    retrieved = mgr.retrieve_secret("smtp_password")
    assert retrieved == "smtp-secret-123"


def test_secret_manager_delete(tmp_path: Path) -> None:
    repo = PlatformRepository(f"sqlite:///{tmp_path / 'secrets_del.db'}")
    mgr = SecretManager(repo=repo)
    mgr.store_secret("api_key", "key-123")
    assert mgr.retrieve_secret("api_key") == "key-123"
    mgr.delete_secret("api_key")
    assert mgr.retrieve_secret("api_key") is None


# =========================================================================
# Platform DB — Enterprise Tables
# =========================================================================

def test_platform_db_create_and_accept_invite(tmp_path: Path) -> None:
    repo = PlatformRepository(f"sqlite:///{tmp_path / 'invites.db'}")
    invite = repo.create_invite("user@example.com", "token-abc-123", "soc_analyst", "admin@example.com")
    assert invite["email"] == "user@example.com"
    assert invite["role"] == "soc_analyst"
    assert invite["accepted_at"] is None

    fetched = repo.get_invite_by_token("token-abc-123")
    assert fetched is not None
    assert fetched["email"] == "user@example.com"

    repo.accept_invite("token-abc-123")
    accepted = repo.get_invite_by_token("token-abc-123")
    assert accepted is None


def test_platform_db_password_reset_flow(tmp_path: Path) -> None:
    from src.auth import UserStore
    store = UserStore(tmp_path / "pw_users.db")
    user = store.create_user("pw@example.com", "password123")
    repo = PlatformRepository(f"sqlite:///{tmp_path / 'pw_resets.db'}")
    reset = repo.create_password_reset(user.id, "reset-token-456")
    assert reset["user_id"] == user.id

    fetched = repo.get_password_reset_by_token("reset-token-456")
    assert fetched is not None
    assert fetched["user_id"] == user.id

    repo.use_password_reset("reset-token-456")
    used = repo.get_password_reset_by_token("reset-token-456")
    assert used is None


def test_platform_db_approval_queue_crud(tmp_path: Path) -> None:
    repo = PlatformRepository(f"sqlite:///{tmp_path / 'approvals.db'}")
    request = repo.create_approval_request(
        approval_id="apr-001",
        request_type="container_restart",
        requester="auto-pipeline",
        summary="Restart web-api container in production",
        details={"container": "web-api", "env": "production"},
    )
    assert request["approval_id"] == "apr-001"
    assert request["status"] == "pending"

    pending = repo.list_approval_requests(status="pending")
    assert len(pending) == 1

    responded = repo.respond_approval("apr-001", "approved", reviewed_by="admin@example.com", comment="Approved after review")
    assert responded is not None
    assert responded["status"] == "approved"
    assert responded["reviewed_by"] == "admin@example.com"

    all_requests = repo.list_approval_requests()
    assert len(all_requests) == 1


def test_platform_db_secrets_tables(tmp_path: Path) -> None:
    repo = PlatformRepository(f"sqlite:///{tmp_path / 'ent_secrets.db'}")
    repo.upsert_secret("test_key", "encrypted-value===", category="generic")
    encrypted = repo.get_secret("test_key")
    assert encrypted == "encrypted-value==="
    meta = repo.get_secret_metadata("test_key")
    assert meta is not None
    assert meta["name"] == "test_key"
    assert meta["category"] == "generic"

    secrets = repo.list_secrets()
    assert len(secrets) == 1
    assert "encrypted_value" not in secrets[0]


def test_platform_db_backup_records(tmp_path: Path) -> None:
    repo = PlatformRepository(f"sqlite:///{tmp_path / 'backup_records.db'}")
    record = repo.save_backup_record(
        file_path="/path/to/backup.zip",
        file_size_bytes=1024,
        label="weekly-backup",
        tables_included=["incidents", "app_settings"],
        knowledge_included=True,
        created_by="admin@example.com",
    )
    assert record["file_path"] == "/path/to/backup.zip"
    assert record["file_size_bytes"] == 1024

    records = repo.list_backup_records()
    assert len(records) == 1
    assert "incidents" in records[0]["tables_included"]


# =========================================================================
# Enhanced Audit Logs
# =========================================================================

def test_enhanced_audit_log_with_before_after(tmp_path: Path) -> None:
    repo = PlatformRepository(f"sqlite:///{tmp_path / 'enhanced_audit.db'}")
    repo.record_audit_log(
        actor="admin@example.com",
        action="update_target",
        resource_type="monitoring_target",
        resource_id="42",
        details={"field": "timeout_seconds", "new_value": 30},
        before_state={"timeout_seconds": 10},
        after_state={"timeout_seconds": 30},
        execution_id="exec-001",
    )
    logs = repo.list_audit_logs_enhanced(limit=10)
    assert len(logs) == 1
    assert logs[0]["execution_id"] == "exec-001"
    assert "before_state" in logs[0]
    assert "after_state" in logs[0]


def test_enhanced_audit_log_filtering(tmp_path: Path) -> None:
    repo = PlatformRepository(f"sqlite:///{tmp_path / 'filtered_audit.db'}")
    repo.record_audit_log("alice", "create", "target", "1", {})
    repo.record_audit_log("bob", "delete", "target", "2", {})
    repo.record_audit_log("alice", "update", "policy", "p1", {})

    alice_logs = repo.list_audit_logs_enhanced(limit=10, actor_filter="alice")
    assert len(alice_logs) == 2

    delete_logs = repo.list_audit_logs_enhanced(limit=10, action_filter="delete")
    assert len(delete_logs) == 1

    policy_logs = repo.list_audit_logs_enhanced(limit=10, resource_type_filter="policy")
    assert len(policy_logs) == 1


# =========================================================================
# Policy CRUD
# =========================================================================

def test_platform_db_policy_crud(tmp_path: Path) -> None:
    repo = PlatformRepository(f"sqlite:///{tmp_path / 'policies_crud.db'}")
    repo.save_policy({
        "name": "test-deny-restart",
        "description": "Deny restarts during business hours",
        "action_pattern": "restart",
        "condition": "business_hours",
        "effect": "deny",
        "priority": 100,
        "enabled": True,
    })
    policies = repo.list_policies()
    assert len(policies) == 1
    assert policies[0]["name"] == "test-deny-restart"

    found = repo.get_policy_by_name("test-deny-restart")
    assert found is not None
    assert found["effect"] == "deny"

    repo.save_policy({
        "name": "test-deny-restart",
        "description": "Updated description",
        "action_pattern": "restart",
        "condition": "business_hours",
        "effect": "deny",
        "priority": 90,
        "enabled": True,
    })
    updated = repo.get_policy_by_name("test-deny-restart")
    assert updated is not None
    assert updated["priority"] == 90

    repo.delete_policy("test-deny-restart")
    assert repo.get_policy_by_name("test-deny-restart") is None


# =========================================================================
# Backup & Restore
# =========================================================================

def test_backup_manager_export_and_restore(tmp_path: Path) -> None:
    repo = PlatformRepository(f"sqlite:///{tmp_path / 'backup_test.db'}")
    repo.create_monitoring_target({"name": "test-target", "target_type": "http", "address": "http://example.com"})
    repo.upsert_setting("session_timeout", "3600")

    bm = BackupManager(repo=repo)
    bm._backup_dir = tmp_path / "backups"
    bm._backup_dir.mkdir(parents=True, exist_ok=True)

    result = bm.export_backup(tables=["monitoring_targets", "app_settings"], include_knowledge=False, label="test")
    assert "file_path" in result
    assert "monitoring_targets" in result["tables"]
    assert result["tables"]["monitoring_targets"] >= 1

    # Verify ZIP contents
    import zipfile, json as _json
    with zipfile.ZipFile(result["file_path"], "r") as zf:
        names = zf.namelist()
        assert "tables/app_settings.json" in names
        assert "tables/monitoring_targets.json" in names
        settings_data = _json.loads(zf.read("tables/app_settings.json"))
        assert any(row["key"] == "session_timeout" and row["value"] == "3600" for row in settings_data)
        targets_data = _json.loads(zf.read("tables/monitoring_targets.json"))
        assert any(row["name"] == "test-target" for row in targets_data)

    # Restore into the same repo after clearing app_settings
    repo._execute("DELETE FROM app_settings")
    restore_result = bm.restore_backup(result["file_path"], tables=["app_settings"], restore_knowledge=False)
    assert "app_settings" in restore_result["tables_restored"]
    settings = repo.get_settings()
    assert settings.get("session_timeout") == "3600"


def test_backup_manager_list_and_delete(tmp_path: Path) -> None:
    repo = PlatformRepository(f"sqlite:///{tmp_path / 'backup_list.db'}")
    bm = BackupManager(repo=repo)
    bm._backup_dir = tmp_path / "backups"
    bm._backup_dir.mkdir(parents=True, exist_ok=True)

    repo.upsert_setting("session_timeout", "1800")
    result = bm.export_backup(tables=["app_settings"], include_knowledge=False, label="list-test")
    backups = bm.list_backups()
    assert len(backups) >= 1
    assert backups[0]["label"] == "list-test"

    assert bm.delete_backup(result["file_path"]) is True
    assert bm.delete_backup("/nonexistent/file.zip") is False
