from __future__ import annotations

import contextlib
import winreg


def _uninstall_roots():
    return [(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"), (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"), (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall")]


def installed_applications() -> list[list[str]]:
    rows = []
    for hive, path in _uninstall_roots():
        try:
            with winreg.OpenKey(hive, path) as root:
                for index in range(winreg.QueryInfoKey(root)[0]):
                    try:
                        with winreg.OpenKey(root, winreg.EnumKey(root, index)) as key:
                            name = winreg.QueryValueEx(key, "DisplayName")[0]
                            if name:
                                rows.append([name, winreg.QueryValueEx(key, "DisplayVersion")[0] if _has(key, "DisplayVersion") else "Unavailable", winreg.QueryValueEx(key, "Publisher")[0] if _has(key, "Publisher") else "Unavailable", winreg.QueryValueEx(key, "InstallDate")[0] if _has(key, "InstallDate") else "Unavailable"])
                    except (OSError, FileNotFoundError):
                        continue
        except OSError:
            continue
    return sorted(rows, key=lambda row: row[0].lower())


def _has(key, name: str) -> bool:
    try:
        winreg.QueryValueEx(key, name)
        return True
    except OSError:
        return False


def startup_items() -> list[list[str]]:
    rows = []
    locations = [(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", "User Run"), (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run", "Machine Run")]
    for hive, path, source in locations:
        try:
            with winreg.OpenKey(hive, path) as key:
                for index in range(winreg.QueryInfoKey(key)[1]):
                    name, value, _ = winreg.EnumValue(key, index)
                    rows.append([name, value, source, "Enabled", "Unavailable"])
        except OSError:
            continue
    return rows


def drivers() -> list[list[str]]:
    rows = []
    try:
        import wmi

        for item in wmi.WMI().Win32_PnPSignedDriver():
            if item.DeviceName:
                rows.append([item.DeviceName, item.DriverVersion or "Unavailable", item.DriverDate or "Unavailable", item.Manufacturer or "Unavailable"])
    except Exception:
        return []
    return rows
