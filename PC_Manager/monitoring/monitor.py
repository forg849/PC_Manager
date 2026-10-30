from __future__ import annotations

import logging

from PySide6.QtCore import QThread, Signal

from PC_Manager.collectors import processes, system
from PC_Manager.monitoring.history import History


class Monitor(QThread):
    snapshot_ready = Signal(dict, list)
    UPDATE_INTERVAL_MS = 2000
    PROCESS_INTERVAL_SECONDS = 10.0
    INVENTORY_INTERVAL_SECONDS = 30.0

    def __init__(self, root, logger: logging.Logger):
        super().__init__()
        self.root = root
        self.logger = logger
        self.running = True
        self.previous = {}
        self.history = None
        self.cached_rows = []
        self.slow_data = None
        self.last_history_write = 0.0

    def run(self) -> None:
        self.history = History(self.root)
        while self.running:
            try:
                data = system.snapshot(self.previous)
                self.previous = data
                now = data["time"]
                refresh_processes = not self.cached_rows or now - getattr(self, "last_process_update", 0.0) >= self.PROCESS_INTERVAL_SECONDS
                rows = self.cached_rows
                if self.slow_data is None:
                    self.slow_data = {"hardware": None, "startup": [], "applications": [], "drivers": []}
                data["hardware"] = self.slow_data["hardware"]
                data["inventory"] = self.slow_data
                if now - self.last_history_write >= 5.0:
                    self.history.add(data)
                    self.last_history_write = now
                self.snapshot_ready.emit(data, rows)
                if refresh_processes and self.running:
                    self.cached_rows = processes.collect()
                    self.last_process_update = now
            except Exception:
                self.logger.exception("monitor update failed")
            self.msleep(self.UPDATE_INTERVAL_MS)

    def stop(self) -> None:
        self.running = False
        self.wait(10000)
