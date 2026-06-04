import sys
import types
import logging
from pathlib import Path

from src.monitor import SystemResourceMonitor


def test_get_stats_returns_cpu_and_ram(tmp_path: Path, monkeypatch) -> None:
    dummy_psutil = types.SimpleNamespace(
        cpu_percent=lambda interval=None: 12.5,
        virtual_memory=lambda: types.SimpleNamespace(percent=42.0),
        disk_usage=lambda path: types.SimpleNamespace(percent=30.0),
    )
    monkeypatch.setitem(sys.modules, "psutil", dummy_psutil)

    logging.getLogger("agentx.monitor").handlers.clear()
    log_path = tmp_path / "agentx.log"
    monitor = SystemResourceMonitor(log_file=str(log_path))

    result = monitor.run({})

    assert result["status"] == "ok"
    assert result["cpu_percent"] == 12.5
    assert result["ram_percent"] == 42.0
    assert result["disk_percent"] == 30.0
    assert result["warnings"] == []
    assert log_path.exists()
