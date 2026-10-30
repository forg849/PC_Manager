from __future__ import annotations

import html
import logging
import sys
import time
from collections import deque
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPushButton, QStackedWidget, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from PC_Manager.monitoring.monitor import Monitor
from PC_Manager.utils.logger import configure_logging

try:
    import pyqtgraph as pg
except ImportError:
    pg = None


NAVIGATION = ["Dashboard", "Processes", "Performance", "Hardware", "Storage", "Network", "Startup", "Applications", "Drivers", "System", "Settings"]


def fmt(value, suffix="", digits=1):
    if isinstance(value, (int, float)):
        return f"{value:.{digits}f}{suffix}"
    return str(value)


class Card(QFrame):
    def __init__(self, title: str):
        super().__init__()
        self.setObjectName("card")
        self.setMinimumHeight(126)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)
        self.title = QLabel(title.upper())
        self.value = QLabel("Unavailable")
        self.value.setObjectName("cardValue")
        self.detail = QLabel("")
        self.detail.setObjectName("muted")
        layout.addWidget(self.title)
        layout.addWidget(self.value)
        layout.addWidget(self.detail)

    def set_data(self, value: str, detail: str = "") -> None:
        self.value.setText(value)
        self.detail.setText(detail)


class Dashboard(QWidget):
    def __init__(self, window: "PCManagerWindow"):
        super().__init__()
        self.window = window
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(16)
        self.heading = QLabel("Dashboard")
        self.heading.setObjectName("heading")
        root.addWidget(self.heading)
        self.summary = QLabel("Waiting for the first system snapshot...")
        self.summary.setObjectName("muted")
        root.addWidget(self.summary)
        cards = QHBoxLayout()
        self.cards = {key: Card(key) for key in ("CPU", "GPU", "RAM", "Disk", "Network")}
        for card in self.cards.values():
            cards.addWidget(card)
        cards.setSpacing(12)
        root.addLayout(cards)
        lower = QHBoxLayout()
        self.health = QLabel("PC HEALTH\nUnavailable")
        self.health.setObjectName("panelText")
        self.top = QLabel("TOP RESOURCE CONSUMERS\nUnavailable")
        self.top.setObjectName("panelText")
        lower.setSpacing(12)
        lower.addWidget(self.health, 1)
        lower.addWidget(self.top, 2)
        root.addLayout(lower, 1)

    def update_data(self, data: dict, rows: list[dict]) -> None:
        gpu = data.get("gpu") or []
        gpu_data = gpu[0] if gpu else {}
        self.cards["CPU"].set_data(fmt(data["cpu"]["usage"], "%"), f"{data['cores']} cores / {data['threads']} threads | {fmt(data['cpu']['frequency'], ' MHz')}")
        self.cards["GPU"].set_data(fmt(gpu_data.get("usage", "Unavailable"), "%"), f"{gpu_data.get('name', 'Unavailable')} | {fmt(gpu_data.get('temperature', 'Unavailable'), ' C')} | {gpu_data.get('source', 'NVML / WMI')}")
        self.cards["RAM"].set_data(fmt(data["ram"]["percent"], "%"), f"{fmt(data['ram']['used'], ' GB')} used of {fmt(data['ram']['total'], ' GB')}")
        self.cards["Disk"].set_data(fmt(data["disk"]["percent"], "%"), f"{fmt(data['disk']['free'], ' GB')} free | R {fmt(data['disk']['read_speed'], ' MB/s')} W {fmt(data['disk']['write_speed'], ' MB/s')}")
        self.cards["Network"].set_data(f"D {fmt(data['network']['download'], ' MB/s')}", f"U {fmt(data['network']['upload'], ' MB/s')} | total {fmt(data['network']['received'], ' GB')} / {fmt(data['network']['sent'], ' GB')}")
        uptime = int(data["uptime"])
        self.summary.setText(f"{data['host']}  |  {data['windows']}  |  uptime {uptime // 86400}d {(uptime % 86400) // 3600:02d}h")
        health = [f"CPU load: {fmt(data['cpu']['usage'], '%')} - {'WARNING' if data['cpu']['usage'] > 90 else 'OK'}", f"RAM: {fmt(data['ram']['percent'], '%')} - {'WARNING' if data['ram']['percent'] > 90 else 'OK'}", f"System disk: {fmt(data['disk']['percent'], '%')} - {'CRITICAL' if data['disk']['percent'] > 95 else 'WARNING' if data['disk']['percent'] > 90 else 'OK'}"]
        gpu_temperature = gpu_data.get("temperature", "Unavailable")
        if gpu_temperature != "Unavailable":
            health.append(f"GPU temperature: {fmt(gpu_temperature, ' C')} - OK")
        self.health.setText("PC HEALTH\n" + "\n".join(health))
        top_cpu = sorted(rows, key=lambda row: row["cpu"], reverse=True)[:5]
        top_ram = sorted(rows, key=lambda row: row["ram_mb"], reverse=True)[:3]
        self.top.setText("TOP RESOURCE CONSUMERS\nCPU\n" + "\n".join(f"{i}. {r['name']} - {r['cpu']:.1f}%" for i, r in enumerate(top_cpu, 1)) + "\n\nRAM\n" + "\n".join(f"{i}. {r['name']} - {r['ram_mb']:.0f} MB" for i, r in enumerate(top_ram, 1)))


class ProcessesPage(QWidget):
    headers = ["Name", "PID", "CPU %", "RAM %", "RAM MB", "GPU %", "VRAM MB", "Disk R", "Disk W", "Threads", "User", "Status", "Path"]
    keys = ["name", "pid", "cpu", "ram_percent", "ram_mb", "gpu", "vram_mb", "disk_read", "disk_write", "threads", "user", "status", "path"]

    def __init__(self):
        super().__init__()
        root = QVBoxLayout(self)
        title = QLabel("Processes")
        title.setObjectName("heading")
        root.addWidget(title)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search process name, PID, user or path...")
        self.search.textChanged.connect(self.refresh)
        root.addWidget(self.search)
        self.table = QTableWidget(0, len(self.headers))
        self.table.setHorizontalHeaderLabels(self.headers)
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.itemSelectionChanged.connect(self.show_details)
        root.addWidget(self.table, 1)
        self.details = QLabel("Select a process for details")
        self.details.setObjectName("panelText")
        root.addWidget(self.details)
        self.rows = []

    def update_rows(self, rows: list[dict]) -> None:
        self.rows = rows
        self.refresh()

    def refresh(self) -> None:
        query = self.search.text().lower()
        visible = [row for row in self.rows if not query or query in " ".join(str(row.get(key, "")) for key in ("name", "pid", "user", "path")).lower()]
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(visible))
        for index, row in enumerate(visible):
            for column, key in enumerate(self.keys):
                value = row.get(key, "Unavailable")
                text = f"{value:.1f}" if isinstance(value, float) else str(value)
                self.table.setItem(index, column, QTableWidgetItem(text))
        self.table.setSortingEnabled(True)

    def show_details(self) -> None:
        items = self.table.selectedItems()
        if not items:
            return
        row = self.rows[items[0].row()] if items[0].row() < len(self.rows) else {}
        self.details.setText(f"{row.get('name')} | PID {row.get('pid')} | CPU {fmt(row.get('cpu'), '%')} | RAM {fmt(row.get('ram_mb'), ' MB')} | threads {row.get('threads')}\nPath: {row.get('path')}\nParent PID: {row.get('ppid')} | Started: {row.get('started', 'Unavailable')}")


class PerformancePage(QWidget):
    def __init__(self):
        super().__init__()
        root = QVBoxLayout(self)
        title = QLabel("Performance")
        title.setObjectName("heading")
        root.addWidget(title)
        self.status = QLabel("Collecting 60-second history...")
        root.addWidget(self.status)
        self.plot = pg.PlotWidget() if pg else QLabel("Install pyqtgraph to display real-time charts")
        if pg:
            self.plot.setBackground("#10151d")
            self.plot.addLegend()
            self.lines = {name: self.plot.plot(pen=color, name=name) for name, color in (("CPU", "#65d6a2"), ("RAM", "#e5b567"), ("Disk", "#e07a9a"), ("Network", "#75a7ff"))}
        root.addWidget(self.plot, 1)
        self.history = {key: deque(maxlen=60) for key in ("cpu", "ram", "disk", "network")}

    def update_data(self, data: dict) -> None:
        self.history["cpu"].append(data["cpu"]["usage"])
        self.history["ram"].append(data["ram"]["percent"])
        self.history["disk"].append(data["disk"]["percent"])
        self.history["network"].append(data["network"]["download"] + data["network"]["upload"])
        self.status.setText(f"CPU {fmt(data['cpu']['usage'], '%')} | RAM {fmt(data['ram']['percent'], '%')} | Disk R/W {fmt(data['disk']['read_speed'], ' MB/s')} / {fmt(data['disk']['write_speed'], ' MB/s')}")
        if pg:
            for key, line in self.lines.items():
                line.setData(list(self.history[key.lower() if key != "Network" else "network"]))


class DataPage(QWidget):
    def __init__(self, title: str, headers: list[str]):
        super().__init__()
        root = QVBoxLayout(self)
        label = QLabel(title)
        label.setObjectName("heading")
        root.addWidget(label)
        self.table = QTableWidget(0, len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setSortingEnabled(True)
        root.addWidget(self.table, 1)
        self.info = QLabel("")
        self.info.setObjectName("muted")
        root.addWidget(self.info)

    def set_rows(self, rows: list[list[str]]) -> None:
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                self.table.setItem(r, c, QTableWidgetItem(str(value)))


class PCManagerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.root_dir = Path(__file__).resolve().parents[1]
        self.logger = configure_logging(self.root_dir)
        self.latest = {}
        self.setWindowTitle("PC Manager")
        self.resize(1440, 900)
        self._build_ui()
        self.monitor = Monitor(self.root_dir, self.logger)
        self.monitor.snapshot_ready.connect(self.on_snapshot)
        self.monitor.start()

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        side = QVBoxLayout(sidebar)
        brand = QLabel("PC MANAGER")
        brand.setObjectName("brand")
        side.addWidget(brand)
        subtitle = QLabel("SYSTEM CONTROL CENTER")
        subtitle.setObjectName("sidebarSubtitle")
        side.addWidget(subtitle)
        self.stack = QStackedWidget()
        self.pages = {}
        self.nav_buttons = []
        for name in NAVIGATION:
            page = self._make_page(name)
            self.pages[name] = page
            self.stack.addWidget(page)
            button = QPushButton(name)
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, target=name: self._select_page(target))
            self.nav_buttons.append(button)
            side.addWidget(button)
        side.addStretch()
        layout.addWidget(sidebar)
        layout.addWidget(self.stack, 1)
        self.stack.currentChanged.connect(self._sync_navigation)
        self._select_page("Dashboard")
        self.setStyleSheet("QWidget { background:#0b1117; color:#edf3f7; font-family:'Segoe UI'; font-size:13px; } #sidebar { background:#111a22; border-right:1px solid #253640; min-width:226px; } #brand { color:#70e0ae; font-size:22px; font-weight:800; padding:20px 18px 2px; letter-spacing:1px; } #sidebarSubtitle { color:#6f8490; font-size:10px; font-weight:700; padding:0 18px 18px; letter-spacing:1px; } #navButton { text-align:left; border:0; border-left:3px solid transparent; border-radius:0; padding:12px 18px; color:#9cafb9; background:transparent; } #navButton:hover { background:#1b2a32; color:#ffffff; } #navButton:checked { background:#193a35; color:#a9f2cd; border-left-color:#70e0ae; font-weight:700; } #heading { color:#f3f7fa; font-size:30px; font-weight:800; padding:0; } #card, #panelText { background:#121e27; border:1px solid #263b46; border-radius:10px; } #card:hover { border-color:#3d6d69; } #cardValue { color:#70e0ae; font-size:26px; font-weight:800; } #muted { color:#7f949f; } QLineEdit, QTableWidget { background:#101920; border:1px solid #29404b; border-radius:6px; padding:8px; } QHeaderView::section { background:#1b2b34; color:#cbd8de; padding:9px; border:0; font-weight:700; } QTableWidget::item:selected { background:#24584e; color:#ffffff; } QTableCornerButton::section { background:#1b2b34; }")

    def _select_page(self, name: str) -> None:
        self.stack.setCurrentWidget(self.pages[name])

    def _sync_navigation(self, index: int) -> None:
        for button_index, button in enumerate(self.nav_buttons):
            button.setChecked(button_index == index)

    def _make_page(self, name: str):
        if name == "Dashboard":
            self.dashboard = Dashboard(self)
            return self.dashboard
        if name == "Processes":
            self.processes = ProcessesPage()
            return self.processes
        if name == "Performance":
            self.performance = PerformancePage()
            return self.performance
        if name == "Hardware":
            self.hardware = DataPage(name, ["Component", "Details", "Status"])
            return self.hardware
        if name == "Storage":
            self.storage = DataPage(name, ["Device", "Mount point", "Filesystem", "Total GB", "Free GB", "Used %"])
            return self.storage
        if name == "Network":
            self.network = DataPage(name, ["Interface", "IP", "MAC", "Received GB", "Sent GB"])
            return self.network
        if name == "System":
            page = DataPage(name, ["Property", "Value"])
            self.system_page = page
            button = QPushButton("Generate PC Report")
            button.clicked.connect(self.generate_report)
            page.layout().insertWidget(1, button)
            return page
        if name == "Startup":
            self.startup = DataPage(name, ["Name", "Path", "Source", "Status", "Publisher"])
            return self.startup
        if name == "Applications":
            self.applications = DataPage(name, ["Name", "Version", "Publisher", "Install date"])
            return self.applications
        if name == "Drivers":
            self.drivers = DataPage(name, ["Device", "Version", "Date", "Manufacturer"])
            return self.drivers
        if name == "Settings":
            page = DataPage(name, ["Setting", "Value"])
            page.set_rows([["CPU warning", "90%"], ["RAM warning", "90%"], ["Disk warning", "90%"], ["Temperature", "Configured by user / unavailable without sensor"]])
            return page
        return DataPage(name, ["Name", "Path", "Status", "Publisher"])

    def on_snapshot(self, data: dict, rows: list[dict]) -> None:
        self.latest = data
        self.dashboard.update_data(data, rows)
        self.processes.update_rows(rows)
        self.performance.update_data(data)
        self.storage.set_rows([[d["device"], d["mountpoint"], d["fstype"], fmt(d["total"]), fmt(d["free"]), fmt(d["percent"], "%")] for d in data["disks"]])
        self.network.set_rows([[n["name"], n["ip"], n["mac"], fmt(n["received"]), fmt(n["sent"])] for n in data["interfaces"]])
        info = data.get("hardware") or {"cpu": data.get("cpu_model", "Unavailable"), "cores": data.get("cores", 0), "threads": data.get("threads", 0), "gpu": data.get("gpu") or [{"name": "Unavailable"}], "ram": data.get("ram"), "motherboard": "Loading...", "bios": "Loading..."}
        gpu = info["gpu"][0] if info["gpu"] else {"name": "Unavailable"}
        self.hardware.set_rows([["CPU", info["cpu"], f"{info['cores']} cores / {info['threads']} threads"], ["GPU", gpu.get("name", "Unavailable"), f"{fmt(gpu.get('usage', 'Unavailable'), '%')}"], ["RAM", fmt(info["ram"]["total"], " GB"), f"{fmt(info['ram']['percent'], '%')} used"], ["Motherboard", info["motherboard"], "Available" if info["motherboard"] != "Unavailable" else "Unavailable"], ["BIOS", info["bios"], "Available" if info["bios"] != "Unavailable" else "Unavailable"]])
        self.system_page.set_rows([["Computer name", data["host"]], ["Windows", data["windows"]], ["Architecture", data["architecture"]], ["User", data["user"]], ["Uptime", f"{int(data['uptime']) // 3600} hours"], ["CPU", data["cpu_model"]], ["RAM", fmt(data["ram"]["total"], " GB")], ["Motherboard", info["motherboard"]]])
        inventory = data.get("inventory", {})
        self.startup.set_rows(inventory.get("startup", []))
        self.applications.set_rows(inventory.get("applications", []))
        self.drivers.set_rows(inventory.get("drivers", []))

    def generate_report(self) -> None:
        if not self.latest:
            QMessageBox.warning(self, "PC Manager", "System data is not available yet.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save PC report", str(self.root_dir / "pc_report.html"), "HTML files (*.html);;Text files (*.txt)")
        if not path:
            return
        data = self.latest
        report = f"<html><body><h1>PC Manager report</h1><pre>{html.escape(repr(data))}</pre></body></html>" if path.lower().endswith(".html") else repr(data)
        try:
            Path(path).write_text(report, encoding="utf-8")
            QMessageBox.information(self, "PC Manager", f"Report saved to {path}")
        except OSError as error:
            self.logger.exception("report generation failed")
            QMessageBox.critical(self, "PC Manager", str(error))

    def closeEvent(self, event) -> None:
        self.monitor.stop()
        super().closeEvent(event)


def run() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = PCManagerWindow()
    window.show()
    return app.exec()
