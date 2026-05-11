"""Low-overhead Raspberry Pi telemetry helpers."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess


def read_temperature_c() -> float | None:
    """Read CPU temperature without requiring a Python dependency."""

    thermal_path = Path("/sys/class/thermal/thermal_zone0/temp")
    if thermal_path.exists():
        try:
            return int(thermal_path.read_text(encoding="utf-8").strip()) / 1000.0
        except (OSError, ValueError):
            return None
    try:
        output = subprocess.check_output(["vcgencmd", "measure_temp"], text=True, timeout=2)
    except (OSError, subprocess.SubprocessError):
        return None
    value = output.strip().replace("temp=", "").replace("'C", "")
    try:
        return float(value)
    except ValueError:
        return None


def read_memory_kb() -> dict[str, int]:
    """Read selected memory counters from /proc/meminfo."""

    wanted = {"MemTotal", "MemAvailable", "SwapTotal", "SwapFree"}
    metrics: dict[str, int] = {}
    try:
        lines = Path("/proc/meminfo").read_text(encoding="utf-8").splitlines()
    except OSError:
        return metrics
    for line in lines:
        key, _, rest = line.partition(":")
        if key in wanted:
            metrics[key] = int(rest.strip().split()[0])
    return metrics


def process_rss_kb(pid: int | None) -> int | None:
    """Read resident set size for a running llama.cpp process."""

    if pid is None:
        return None
    statm = Path(f"/proc/{pid}/statm")
    try:
        pages = int(statm.read_text(encoding="utf-8").split()[1])
    except (OSError, IndexError, ValueError):
        return None
    return pages * (os.sysconf("SC_PAGE_SIZE") // 1024)
