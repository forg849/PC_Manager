from __future__ import annotations

from typing import Any

import psutil


def collect() -> list[dict[str, Any]]:
    rows = []
    for process in psutil.process_iter(["pid", "name", "status", "num_threads", "memory_percent", "memory_info"]):
        try:
            info = process.info
            memory_info = info.get("memory_info")
            rows.append({"name": info.get("name") or "Unavailable", "pid": info["pid"], "cpu": process.cpu_percent(None), "ram_percent": info.get("memory_percent", 0.0), "ram_mb": memory_info.rss / 1024**2 if memory_info else 0.0, "gpu": "Unavailable", "gpu_engine": "Unavailable", "vram_mb": "Unavailable", "disk_read": "Unavailable", "disk_write": "Unavailable", "network": "Unavailable", "threads": info.get("num_threads", 0), "path": "Unavailable", "user": "Unavailable", "status": info.get("status") or "Unavailable", "started": "Unavailable", "ppid": "Unavailable"})
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
        except Exception:
            continue
    return rows
