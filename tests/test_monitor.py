import sys
import types
import logging
from pathlib import Path

from src.monitor import SystemResourceMonitor


def test_get_stats_returns_cpu_and_ram(tmp_path: Path, monkeypatch) -> None:
    dummy_psutil = types.SimpleNamespace(
        cpu_percent=lambda interval=None: 12.5,
        cpu_count=lambda: 4,
        virtual_memory=lambda: types.SimpleNamespace(percent=42.0, total=16 * 1024**3, used=6 * 1024**3),
        disk_usage=lambda path: types.SimpleNamespace(percent=30.0, free=50 * 1024**3, total=100 * 1024**3),
        net_io_counters=lambda: types.SimpleNamespace(bytes_sent=1000, bytes_recv=2000, packets_sent=10, packets_recv=20),
        boot_time=lambda: 1000.0,
        pids=lambda: [1, 2, 3],
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
