"""Backup & Restore — export/import for configs, incidents, and knowledge."""

from __future__ import annotations

import json
import os
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class BackupManager:
    """Export and import AegisNex configuration, incidents, and knowledge data."""

    EXPORT_TABLES = frozenset({
        "incidents",
        "notifications",
        "remediation_actions",
        "incident_transitions",
        "monitoring_targets",
        "check_results",
        "metrics_snapshots",
        "app_settings",
        "notification_channels",
        "alert_rules",
        "api_keys",
        "policies",
    })

    def __init__(self, repo: Any | None = None) -> None:
        self._repo = repo
        self._backup_dir = Path(os.getenv("AEGISNEX_BACKUP_DIR", "data/backups"))
        self._backup_dir.mkdir(parents=True, exist_ok=True)

    def export_backup(
        self,
        tables: list[str] | None = None,
        include_knowledge: bool = True,
        label: str = "",
    ) -> dict[str, Any]:
        """Export selected tables and knowledge to a zip archive.

        Returns metadata about the created backup file.
        """
        export_tables = tables or list(self.EXPORT_TABLES)
        timestamp = _utc_now()
        safe_ts = timestamp.replace(":", "-").replace("+", "-")
        label_part = f"_{label}" if label else ""
        filename = f"aegisnex_backup_{safe_ts}{label_part}.zip"
        backup_path = self._backup_dir / filename

        manifest: dict[str, Any] = {
            "backup_version": "1.0",
            "created_at": timestamp,
            "label": label,
            "tables": {},
            "knowledge_included": include_knowledge,
        }

        with zipfile.ZipFile(str(backup_path), "w", zipfile.ZIP_DEFLATED) as zf:
            if self._repo is not None:
                for table in export_tables:
                    try:
                        rows = self._repo.fetch_all(table)
                        data = json.dumps(rows, default=str, sort_keys=True)
                        zf.writestr(f"tables/{table}.json", data)
                        manifest["tables"][table] = len(rows)
                    except Exception as exc:
                        manifest["tables"][table] = {"error": str(exc)}

            if include_knowledge:
                knowledge_dir = Path("data/knowledge")
                if knowledge_dir.exists():
                    for fpath in knowledge_dir.rglob("*"):
                        if fpath.is_file():
                            arcname = f"knowledge/{fpath.relative_to(knowledge_dir.parent)}"
                            zf.write(str(fpath), arcname)
                    manifest["knowledge_size"] = sum(
                        f.stat().st_size for f in knowledge_dir.rglob("*") if f.is_file()
                    )

            zf.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True))

        manifest["file_path"] = str(backup_path)
        manifest["file_size_bytes"] = backup_path.stat().st_size
        return manifest

    def list_backups(self) -> list[dict[str, Any]]:
        """List all available backup archives."""
        backups: list[dict[str, Any]] = []
        if not self._backup_dir.exists():
            return backups
        for fpath in sorted(self._backup_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if fpath.suffix == ".zip":
                manifest = self._read_manifest(fpath)
                backups.append({
                    "file_path": str(fpath),
                    "file_name": fpath.name,
                    "file_size_bytes": fpath.stat().st_size,
                    "created_at": manifest.get("created_at", ""),
                    "label": manifest.get("label", ""),
                    "tables": manifest.get("tables", {}),
                    "knowledge_included": manifest.get("knowledge_included", False),
                })
        return backups

    def _read_manifest(self, path: Path) -> dict[str, Any]:
        try:
            with zipfile.ZipFile(str(path), "r") as zf:
                if "manifest.json" in zf.namelist():
                    return json.loads(zf.read("manifest.json"))
        except Exception:
            pass
        return {}

    def restore_backup(
        self,
        file_path: str,
        tables: list[str] | None = None,
        restore_knowledge: bool = True,
        actor: str = "system",
    ) -> dict[str, Any]:
        """Restore data from a backup archive.

        Returns the count of records restored per table.
        """
        backup_path = Path(file_path)
        if not backup_path.exists():
            return {"error": f"Backup file not found: {file_path}"}

        result: dict[str, Any] = {
            "tables_restored": {},
            "knowledge_restored": False,
            "errors": [],
        }

        with zipfile.ZipFile(str(backup_path), "r") as zf:
            if self._repo is not None:
                table_files = [n for n in zf.namelist() if n.startswith("tables/") and n.endswith(".json")]
                for tf in table_files:
                    table_name = tf[len("tables/"):-len(".json")]
                    if tables and table_name not in tables:
                        continue
                    try:
                        data = json.loads(zf.read(tf))
                        restored = self._restore_table(table_name, data, actor=actor)
                        result["tables_restored"][table_name] = restored
                    except Exception as exc:
                        result["errors"].append(f"{table_name}: {exc}")

            if restore_knowledge:
                knowledge_files = [n for n in zf.namelist() if n.startswith("knowledge/")]
                if knowledge_files:
                    restore_dir = Path("data/restored_knowledge")
                    restore_dir.mkdir(parents=True, exist_ok=True)
                    for kf in knowledge_files:
                        try:
                            zf.extract(kf, str(restore_dir))
                        except Exception as exc:
                            result["errors"].append(f"knowledge/{kf}: {exc}")
                    result["knowledge_restored"] = True
                    result["knowledge_path"] = str(restore_dir)

        return result

    def _restore_table(self, table_name: str, rows: list[dict[str, Any]], actor: str = "system") -> int:
        """Restore rows into a table using the repository."""
        if not rows or self._repo is None:
            return 0
        count = 0
        for row in rows:
            try:
                if hasattr(self._repo, f"restore_{table_name}"):
                    getattr(self._repo, f"restore_{table_name}")(row)
                elif table_name == "app_settings":
                    key = row.get("key")
                    value = row.get("value", "")
                    if key:
                        self._repo.upsert_setting(key, value)
                elif table_name in ("incidents", "notifications", "remediation_actions",
                                    "incident_transitions", "monitoring_targets",
                                    "check_results", "metrics_snapshots",
                                    "notification_channels", "alert_rules"):
                    self._restore_generic(table_name, row)
                count += 1
            except Exception:
                pass
        self._repo.record_audit_log(actor, "restore", table_name, f"{count} rows", {})
        return count

    def _restore_generic(self, table_name: str, row: dict[str, Any]) -> None:
        """Generic restore by direct SQL insert."""
        if self._repo is None:
            return
        columns = ", ".join(row.keys())
        placeholders = ", ".join([self._repo.placeholder] * len(row))
        values = list(row.values())
        self._repo._execute(
            f"INSERT OR IGNORE INTO {table_name} ({columns}) VALUES ({placeholders})",
            values,
        )

    def delete_backup(self, file_path: str) -> bool:
        """Delete a backup archive."""
        path = Path(file_path)
        if path.exists() and path.suffix == ".zip":
            path.unlink()
            return True
        return False
