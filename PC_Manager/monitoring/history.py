from __future__ import annotations

import sqlite3
from pathlib import Path


class History:
    def __init__(self, root: Path):
        self.connection = sqlite3.connect(root / "history.db", check_same_thread=False)
        self.connection.execute("CREATE TABLE IF NOT EXISTS metrics (created REAL NOT NULL, cpu REAL, gpu REAL, ram REAL, disk REAL, download REAL, upload REAL)")
        self.connection.commit()

    def add(self, data: dict) -> None:
        gpu = data.get("gpu") or []
        self.connection.execute("INSERT INTO metrics VALUES (unixepoch(), ?, ?, ?, ?, ?, ?)", (data["cpu"]["usage"], gpu[0].get("usage", 0) if gpu else 0, data["ram"]["percent"], data["disk"]["percent"], data["network"]["download"], data["network"]["upload"]))
        self.connection.commit()

    def recent(self, limit: int = 60) -> list[tuple]:
        return list(self.connection.execute("SELECT created, cpu, gpu, ram, disk, download, upload FROM metrics ORDER BY created DESC LIMIT ?", (limit,)))[::-1]
