from __future__ import annotations

import getpass
import os
import platform
import socket
import threading
import time
import warnings
from typing import Any

import psutil


_GPU_LOCK = threading.Lock()


def _safe(call, default="Unavailable"):
    try:
        value = call()
        return default if value in (None, "") else value
    except Exception:
        return default


def _gpu_info() -> list[dict[str, Any]]:
    with _GPU_LOCK:
        return _gpu_info_uncached()


def _gpu_info_uncached() -> list[dict[str, Any]]:
    if getattr(_gpu_info_uncached, "disabled", False):
        return _wmi_gpu_info()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            import pynvml

        if not getattr(_gpu_info_uncached, "initialized", False):
            pynvml.nvmlInit()
            _gpu_info_uncached.initialized = True
        result = []
        for index in range(pynvml.nvmlDeviceGetCount()):
            handle = pynvml.nvmlDeviceGetHandleByIndex(index)
            memory = pynvml.nvmlDeviceGetMemoryInfo(handle)
            utilization = pynvml.nvmlDeviceGetUtilizationRates(handle)
            result.append({"name": pynvml.nvmlDeviceGetName(handle).decode(errors="replace"), "usage": float(utilization.gpu), "temperature": _safe(lambda: float(pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU))), "vram_used": memory.used / 1024**2, "vram_total": memory.total / 1024**2, "power": _safe(lambda: pynvml.nvmlDeviceGetPowerUsage(handle) / 1000), "clock": _safe(lambda: pynvml.nvmlDeviceGetClockInfo(handle, pynvml.NVML_CLOCK_GRAPHICS)), "driver": _safe(lambda: pynvml.nvmlSystemGetDriverVersion().decode(errors="replace"))})
        return result or _wmi_gpu_info()
    except Exception:
        _gpu_info_uncached.disabled = True
        return _wmi_gpu_info()


def _wmi_gpu_info() -> list[dict[str, Any]]:
    cached = getattr(_wmi_gpu_info, "cached", None)
    if cached is not None:
        if time.monotonic() - getattr(_wmi_gpu_info, "usage_updated", 0.0) < 15.0:
            return _wmi_gpu_info.usage_cache
        _wmi_gpu_info.usage_cache = _wmi_gpu_usage(cached)
        _wmi_gpu_info.usage_updated = time.monotonic()
        return _wmi_gpu_info.usage_cache
    result = []
    try:
        import wmi

        for item in wmi.WMI().Win32_VideoController():
            name = item.Name or "Unavailable"
            memory = item.AdapterRAM
            result.append({"name": name, "usage": "Unavailable", "temperature": "Unavailable", "vram_used": "Unavailable", "vram_total": memory / 1024**2 if isinstance(memory, int) and memory > 0 else "Unavailable", "power": "Unavailable", "clock": "Unavailable", "driver": item.DriverVersion or "Unavailable", "source": "Windows WMI"})
    except Exception:
        result = [{"name": "Unavailable", "usage": "Unavailable", "temperature": "Unavailable", "vram_used": "Unavailable", "vram_total": "Unavailable", "power": "Unavailable", "clock": "Unavailable", "driver": "Unavailable", "source": "Unavailable"}]
    _wmi_gpu_info.cached = result
    _wmi_gpu_info.usage_cache = _wmi_gpu_usage(result)
    _wmi_gpu_info.usage_updated = time.monotonic()
    return _wmi_gpu_info.usage_cache


def _wmi_gpu_usage(gpus: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not gpus or gpus[0].get("name") == "Unavailable":
        return gpus
    try:
        import wmi

        usage = 0.0
        for engine in wmi.WMI().Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine():
            if "engtype_3D" in (engine.Name or ""):
                usage = max(usage, float(engine.UtilizationPercentage or 0))
        return [dict(gpu, usage=round(min(100.0, usage), 1)) for gpu in gpus]
    except Exception:
        return gpus


def snapshot(previous: dict[str, Any] | None = None) -> dict[str, Any]:
    previous = previous or {}
    cpu_percent = psutil.cpu_percent(interval=None)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage(os.environ.get("SystemDrive", "C:\\") + "\\")
    disk_io = psutil.disk_io_counters()
    net_io = psutil.net_io_counters()
    now = time.monotonic()
    elapsed = max(now - previous.get("time", now), 0.001)
    old_disk = previous.get("disk_io")
    old_net = previous.get("net_io")
    static = previous.get("static", {})
    if now - static.get("updated", 0.0) >= 10.0:
        static = {"updated": now, "disks": _disk_details(), "interfaces": _interfaces()}
    return {"time": now, "cpu": {"usage": cpu_percent, "per_core": psutil.cpu_percent(interval=None, percpu=True), "frequency": _safe(lambda: psutil.cpu_freq().current)}, "ram": {"used": memory.used / 1024**3, "available": memory.available / 1024**3, "total": memory.total / 1024**3, "percent": memory.percent}, "disk": {"used": disk.used / 1024**3, "free": disk.free / 1024**3, "total": disk.total / 1024**3, "percent": disk.percent, "read_speed": ((disk_io.read_bytes - old_disk.read_bytes) / elapsed / 1024**2) if old_disk else 0.0, "write_speed": ((disk_io.write_bytes - old_disk.write_bytes) / elapsed / 1024**2) if old_disk else 0.0}, "network": {"download": ((net_io.bytes_recv - old_net.bytes_recv) / elapsed / 1024**2) if old_net else 0.0, "upload": ((net_io.bytes_sent - old_net.bytes_sent) / elapsed / 1024**2) if old_net else 0.0, "received": net_io.bytes_recv / 1024**3, "sent": net_io.bytes_sent / 1024**3}, "gpu": _gpu_info(), "disk_io": disk_io, "net_io": net_io, "static": static, "host": previous.get("host", socket.gethostname()), "user": previous.get("user", getpass.getuser()), "windows": previous.get("windows", f"{platform.system()} {platform.release()} ({platform.version()})"), "architecture": previous.get("architecture", platform.machine()), "uptime": time.time() - psutil.boot_time(), "cpu_model": previous.get("cpu_model", platform.processor() or "Unavailable"), "cores": previous.get("cores", psutil.cpu_count(logical=False) or 0), "threads": previous.get("threads", psutil.cpu_count(logical=True) or 0), "disks": static["disks"], "interfaces": static["interfaces"]}


def _disk_details() -> list[dict[str, Any]]:
    result = []
    for partition in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(partition.mountpoint)
            result.append({"device": partition.device, "mountpoint": partition.mountpoint, "fstype": partition.fstype, "total": usage.total / 1024**3, "free": usage.free / 1024**3, "used": usage.used / 1024**3, "percent": usage.percent})
        except (OSError, PermissionError):
            continue
    return result


def _interfaces() -> list[dict[str, Any]]:
    counters = psutil.net_io_counters(pernic=True)
    result = []
    for name, addresses in psutil.net_if_addrs().items():
        ips = [address.address for address in addresses if address.family == socket.AF_INET]
        mac = next((address.address for address in addresses if str(address.family).endswith("-17") or address.family == getattr(psutil, "AF_LINK", object())), "Unavailable")
        counter = counters.get(name)
        result.append({"name": name, "ip": ", ".join(ips) or "Unavailable", "mac": mac, "received": counter.bytes_recv / 1024**3 if counter else 0, "sent": counter.bytes_sent / 1024**3 if counter else 0})
    return result


def hardware_details(data: dict[str, Any]) -> dict[str, Any]:
    details = {"cpu": data.get("cpu_model", "Unavailable"), "cores": data.get("cores"), "threads": data.get("threads"), "gpu": data.get("gpu") or [{"name": "Unavailable"}], "ram": data.get("ram"), "motherboard": "Unavailable", "bios": "Unavailable"}
    try:
        import wmi

        client = wmi.WMI()
        board = client.Win32_BaseBoard()[0]
        bios = client.Win32_BIOS()[0]
        details["motherboard"] = f"{board.Manufacturer} {board.Product}"
        details["bios"] = f"{bios.Manufacturer} {bios.SMBIOSBIOSVersion}"
    except Exception:
        pass
    return details
