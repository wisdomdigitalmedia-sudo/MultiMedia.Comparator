#!/usr/bin/env python3
"""
Media Catalog agent (Windows, Linux, or Mac file host).

Run this on the machine that holds the disks so Comparator on another PC can
list volumes (even when they are not shared over SMB) and scan them.

  python agent.py
  python agent.py --host 0.0.0.0 --port 8766 --token optional-secret

Then on the catalog PC: Add drive → media host → paste this PC's address.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import stat
import string
import subprocess
import sys
import tarfile
import tempfile
import threading
import traceback
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

# Allow running from project root so scanner/config import works
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import MEDIA_EXTENSIONS  # noqa: E402
from scanner import normalize_scan_path, scan_root  # noqa: E402

AGENT_TOKEN = os.environ.get("MEDIA_CATALOG_AGENT_TOKEN", "")
AGENT_HOST = "0.0.0.0"
AGENT_PORT = 8766
AGENT_VERSION = "1.5.2"  # 1.5.2: POST /api/delete for confirmed extra copies

_FFPROBE_LOCK = threading.Lock()
_FFPROBE_PATH: str | None = None
_FFPROBE_URLS_WIN = (
    "https://github.com/ffbinaries/ffbinaries-prebuilt/releases/download/v6.1/ffprobe-6.1-win-64.zip",
    "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
)
_FFPROBE_URLS_LINUX = (
    "https://github.com/ffbinaries/ffbinaries-prebuilt/releases/download/v6.1/ffprobe-6.1-linux-64.zip",
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz",
)
_FFPROBE_URLS_MAC = (
    "https://github.com/ffbinaries/ffbinaries-prebuilt/releases/download/v6.1/ffprobe-6.1-osx-64.zip",
)
_FFPROBE_UA = "MediaCatalogAgent/1.5 (ffprobe-install)"


def _ffprobe_urls() -> tuple[str, ...]:
    system = platform.system()
    if system == "Windows":
        return _FFPROBE_URLS_WIN
    if system == "Darwin":
        return _FFPROBE_URLS_MAC
    return _FFPROBE_URLS_LINUX

# Cache full-map SMART for a few seconds (many UI clicks / multi-drive refresh)
_SMART_MAP_CACHE: dict[str, Any] = {"ts": 0.0, "data": {}}
_SMART_MAP_TTL = 30.0


def _run_powershell(script: str, timeout: float = 90.0) -> tuple[int, str, str]:
    """Run a PowerShell snippet; return (code, stdout, stderr)."""
    exe = shutil.which("powershell") or shutil.which("pwsh")
    if not exe:
        return 1, "", "powershell not found"
    try:
        proc = subprocess.run(
            [
                exe,
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                script,
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    except subprocess.TimeoutExpired:
        return 1, "", "powershell timed out"
    except OSError as exc:
        return 1, "", str(exc)


def windows_smart_map(force: bool = False) -> dict[str, dict[str, Any]]:
    """
    Map drive letter → health / media / label.

    Strategy (most reliable for many USB externals):
      1) Find every letter that exists via Test-Path / disk_usage
      2) Per letter: Get-Volume + Get-Partition -DriveLetter + PhysicalDisk
      3) Never depend only on Get-Partition pipeline (misses many volumes)
    """
    import time

    if platform.system() != "Windows":
        return {}

    now = time.time()
    if (
        not force
        and _SMART_MAP_CACHE["data"]
        and (now - float(_SMART_MAP_CACHE["ts"])) < _SMART_MAP_TTL
    ):
        return dict(_SMART_MAP_CACHE["data"])

    result: dict[str, dict[str, Any]] = {}

    # Always seed letters that Python can see (matches capacity reporting)
    for ch in string.ascii_uppercase:
        root = f"{ch}:\\"
        if not os.path.exists(root):
            continue
        entry: dict[str, Any] = {
            "letter": ch,
            "health": "Unknown",
            "operational": "",
            "model": "",
            "volume_label": "",
            "media": "",
            "bus": "",
            "serial": "",
            "source": "disk_usage",
            "drive_type": "",
            "error": "",
            "total_bytes": None,
            "free_bytes": None,
            "used_bytes": None,
            "size_bytes": None,
        }
        try:
            usage = shutil.disk_usage(root)
            entry["total_bytes"] = usage.total
            entry["free_bytes"] = usage.free
            entry["used_bytes"] = usage.used
            entry["size_bytes"] = usage.total
        except OSError as exc:
            entry["error"] = str(exc)
        result[ch] = entry

    # Enrich all known letters in one PowerShell pass
    letters = "".join(sorted(result.keys()))
    if letters:
        script = rf"""
$ErrorActionPreference = 'SilentlyContinue'
$letters = '{letters}'.ToCharArray()
$rows = @()
foreach ($ch in $letters) {{
  $L = [string]$ch
  $row = [ordered]@{{
    letter = $L
    health = 'Unknown'
    operational = ''
    model = ''
    volume_label = ''
    media = ''
    bus = ''
    serial = ''
    source = 'Get-Volume'
    drive_type = ''
    error = ''
    size_bytes = $null
  }}
  try {{
    $vol = Get-Volume -DriveLetter $L -ErrorAction SilentlyContinue
    if ($vol) {{
      $row.drive_type = [string]$vol.DriveType
      $row.volume_label = [string]$vol.FileSystemLabel
      $row.model = $row.volume_label
      if ($vol.Size) {{ $row.size_bytes = [int64]$vol.Size }}
      if ($vol.DriveType -match 'Network') {{
        $row.error = 'Network volume — SMART is on the NAS, not this PC'
        $rows += [pscustomobject]$row
        continue
      }}
    }}
    $part = Get-Partition -DriveLetter $L -ErrorAction SilentlyContinue
    $disk = $null
    $phys = $null
    if ($part) {{
      $disk = Get-Disk -Number $part.DiskNumber -ErrorAction SilentlyContinue
    }}
    if ($disk) {{
      $row.health = if ($disk.HealthStatus) {{ [string]$disk.HealthStatus }} else {{ 'Unknown' }}
      $row.operational = [string]$disk.OperationalStatus
      if ($disk.FriendlyName) {{ $row.model = [string]$disk.FriendlyName }}
      $row.serial = [string]$disk.SerialNumber
      $row.bus = [string]$disk.BusType
      $row.source = 'Get-Disk'
      $phys = Get-PhysicalDisk -DeviceNumber $disk.Number -ErrorAction SilentlyContinue
      if (-not $phys) {{
        $phys = Get-PhysicalDisk | Where-Object {{ $_.DeviceId -eq $disk.Number }} | Select-Object -First 1
      }}
    }}
    if ($phys) {{
      $row.health = [string]$phys.HealthStatus
      $row.operational = [string]$phys.OperationalStatus
      if ($phys.FriendlyName) {{ $row.model = [string]$phys.FriendlyName }}
      $row.media = [string]$phys.MediaType
      $row.bus = [string]$phys.BusType
      $row.serial = [string]$phys.SerialNumber
      if ($phys.Size) {{ $row.size_bytes = [int64]$phys.Size }}
      $row.source = 'Get-PhysicalDisk'
    }}
    if (-not $part -and -not $vol) {{
      $row.error = 'No Get-Volume/Get-Partition object (still mounted for apps)'
      $row.source = 'letter-only'
    }} elseif (-not $phys -and -not $disk) {{
      $row.error = 'No physical disk mapping — use CrystalDiskInfo (run agent as Admin)'
    }}
  }} catch {{
    $row.error = $_.Exception.Message
    $row.source = 'error'
  }}
  $rows += [pscustomobject]$row
}}
@($rows) | ConvertTo-Json -Compress -Depth 4
"""
        code, out, err = _run_powershell(script, timeout=120)
        raw = (out or "").strip()
        data = None
        if raw:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                start = raw.find("[")
                if start < 0:
                    start = raw.find("{")
                if start >= 0:
                    try:
                        data = json.loads(raw[start:])
                    except json.JSONDecodeError:
                        data = None
        rows: list[Any] = []
        if isinstance(data, list):
            rows = data
        elif isinstance(data, dict):
            rows = [data] if "letter" in data else []

        for row in rows:
            if not isinstance(row, dict):
                continue
            letter = str(row.get("letter") or "").strip().upper()[:1]
            if letter not in result:
                continue
            base = result[letter]
            for key in (
                "health",
                "operational",
                "model",
                "volume_label",
                "media",
                "bus",
                "serial",
                "source",
                "drive_type",
                "error",
            ):
                val = row.get(key)
                if val is not None and str(val).strip() != "":
                    base[key] = val
            if row.get("size_bytes") is not None and base.get("total_bytes") is None:
                try:
                    base["size_bytes"] = int(row["size_bytes"])
                except (TypeError, ValueError):
                    pass
            # Normalize empty health
            if not base.get("health"):
                base["health"] = "Unknown"
            # Healthy default for local fixed volumes with no errors when Windows
            # returns blank but volume is readable — keep Unknown rather than fake Good

    _SMART_MAP_CACHE["ts"] = now
    _SMART_MAP_CACHE["data"] = result
    return dict(result)


def smart_for_path(path_str: str) -> dict[str, Any]:
    """S.M.A.R.T. / health report for a Windows path or drive root. Always returns JSON."""
    # Don't require path to exist as a directory for SMART (letter is enough)
    text = str(path_str or "").strip().replace("\\", "/")
    letter = ""
    m = re.match(r"^([A-Za-z]):", text)
    if m:
        letter = m.group(1).upper()
    elif re.fullmatch(r"[A-Za-z]", text):
        letter = text.upper()
    else:
        try:
            path = normalize_scan_path(path_str)
            text = str(path)
            m = re.match(r"^([A-Za-z]):", text)
            if m:
                letter = m.group(1).upper()
        except Exception:  # noqa: BLE001
            pass

    report: dict[str, Any] = {
        "status": "unknown",
        "status_raw": "Unknown",
        "temperature_c": None,
        "model": "",
        "serial": "",
        "media": "",
        "bus": "",
        "source": "",
        "detail": "",
        "ok": True,  # soft-ok: UI should not treat as hard failure
        "path": text,
        "letter": letter,
        "agent_version": AGENT_VERSION,
    }

    if platform.system() == "Windows" and letter:
        # Capacity (size / free) — always try, independent of SMART
        try:
            usage = shutil.disk_usage(f"{letter}:\\")
            report["total_bytes"] = usage.total
            report["free_bytes"] = usage.free
            report["used_bytes"] = usage.used
        except OSError:
            pass

        # 1) Preferred: CrystalDiskInfo (best SMART / health / sector data)
        cdi_used = False
        cdi_warning = ""
        try:
            from crystaldisk import crystaldisk_report_for_letter, find_crystaldisk_exe

            if find_crystaldisk_exe():
                cdi = crystaldisk_report_for_letter(letter, force=False)
                cdi_warning = str(cdi.get("cdi_warning") or "")
                # Accept any real health status from CDI (Good/Caution/Bad)
                raw_st = str(cdi.get("status_raw") or "").strip()
                if cdi.get("ok") and raw_st and raw_st.lower() not in {
                    "not listed",
                    "unavailable",
                    "",
                }:
                    for k, v in cdi.items():
                        if v is not None and v != "":
                            report[k] = v
                    report["source"] = "crystaldiskinfo"
                    cdi_used = True
                elif cdi.get("detail"):
                    cdi_warning = cdi_warning or str(cdi.get("detail"))
            else:
                cdi_warning = "CrystalDiskInfo executable not found"
        except Exception as exc:  # noqa: BLE001
            cdi_warning = f"CrystalDiskInfo error: {exc}"

        # 2) Windows Storage API — always enrich; use as health if CDI missing
        smap = windows_smart_map()
        entry = smap.get(letter)
        if entry:
            if not report.get("volume_label"):
                report["volume_label"] = str(entry.get("volume_label") or "")
            if not report.get("model"):
                report["model"] = str(entry.get("model") or "")
            if report.get("volume_label") and not report.get("model"):
                report["model"] = report["volume_label"]
            if not report.get("serial"):
                report["serial"] = str(entry.get("serial") or "")
            if not cdi_used:
                health = str(entry.get("health") or "Unknown")
                report["status_raw"] = health
                report["status"] = health
                report["source"] = str(entry.get("source") or "windows")
                detail_parts = [
                    p
                    for p in (
                        str(entry.get("error") or ""),
                        str(entry.get("operational") or ""),
                        cdi_warning,
                    )
                    if p
                ]
                report["detail"] = " · ".join(detail_parts) or (
                    f"Windows health: {health}"
                )
            else:
                # Keep CDI health; append warning about cache/admin if any
                if cdi_warning and cdi_warning not in str(report.get("detail") or ""):
                    report["detail"] = (
                        str(report.get("detail") or "") + " · " + cdi_warning
                    ).strip(" ·")
            if not report.get("media"):
                report["media"] = str(entry.get("media") or "")
            if not report.get("bus"):
                report["bus"] = str(entry.get("bus") or "")
            report["operational"] = str(entry.get("operational") or "")
            report["drive_type"] = str(entry.get("drive_type") or "")
            report["size_bytes"] = entry.get("size_bytes")
            if entry.get("total_bytes") is not None:
                report["total_bytes"] = entry.get("total_bytes")
            if entry.get("free_bytes") is not None:
                report["free_bytes"] = entry.get("free_bytes")
            if entry.get("used_bytes") is not None:
                report["used_bytes"] = entry.get("used_bytes")
            try:
                from smart_health import classify_drive_hardware

                hw, hw_label = classify_drive_hardware(
                    media=str(report.get("media") or ""),
                    bus=str(report.get("bus") or ""),
                    drive_type=str(report.get("drive_type") or ""),
                    model=str(report.get("model") or ""),
                    detail=str(report.get("detail") or ""),
                    name=str(report.get("volume_label") or ""),
                    root_path=f"{letter}:/",
                )
                report["hardware_type"] = hw
                report["hardware_label"] = hw_label
            except Exception:  # noqa: BLE001
                pass
        elif not cdi_used:
            report["detail"] = (
                f"No health data for {letter}: — "
                + (cdi_warning or "volume mapping failed")
            )
            report["source"] = report.get("source") or "windows-missing"
            if cdi_warning:
                report["detail"] = cdi_warning

        # 3) smartctl fallback if CDI missing sector attrs
        smartctl = shutil.which("smartctl")
        if smartctl and not report.get("sector_attrs_available"):
            try:
                from smart_health import _parse_smartctl, merge_status

                proc = subprocess.run(
                    [smartctl, "-H", "-A", "-i", f"{letter}:"],
                    capture_output=True,
                    text=True,
                    timeout=25,
                )
                blob = (proc.stdout or "") + "\n" + (proc.stderr or "")
                parsed = _parse_smartctl(blob)
                if not cdi_used and parsed.get("status_raw"):
                    report["status_raw"] = parsed["status_raw"]
                    report["status"] = merge_status(
                        str(report.get("status") or "unknown"),
                        str(parsed.get("status") or ""),
                    )
                if parsed.get("temperature_c") is not None and report.get(
                    "temperature_c"
                ) is None:
                    report["temperature_c"] = parsed["temperature_c"]
                for key in (
                    "sector_attrs_available",
                    "sector_reallocated",
                    "sector_pending",
                    "sector_uncorrectable",
                    "sector_crc",
                    "sector_reported_uncorrect",
                    "nvme_media_errors",
                    "sector_summary",
                    "sector_note",
                    "sector_attrs",
                ):
                    if key in parsed and parsed[key] is not None:
                        if key == "sector_attrs_available" or not report.get(key):
                            report[key] = parsed[key]
                if parsed.get("sector_attrs_available") and not cdi_used:
                    report["source"] = f"smartctl:{letter}:"
                    report["detail"] = parsed.get("detail") or report.get("detail")
            except (OSError, subprocess.TimeoutExpired, Exception):  # noqa: BLE001
                pass
    elif platform.system() != "Windows":
        try:
            from smart_health import probe_local_smart

            local = probe_local_smart(path_str)
            report.update(local)
            report["path"] = text
            report["letter"] = letter
            report["ok"] = True
            report["agent_version"] = AGENT_VERSION
        except Exception as exc:  # noqa: BLE001
            report["detail"] = str(exc)
    else:
        report["detail"] = "Could not determine drive letter from path"
        report["source"] = "parse"

    if not report.get("detail") and str(report.get("status_raw", "")).lower() in {
        "unknown",
        "",
    }:
        report["detail"] = (
            "Health unknown — common for USB enclosures, some external docks, "
            "RAID virtual disks, and network/NAS mappings."
        )
    return report


def list_local_drives() -> list[dict[str, Any]]:
    """Return fixed drives / volumes available on this machine."""
    drives: list[dict[str, Any]] = []
    system = platform.system()

    if system == "Windows":
        for letter in string.ascii_uppercase:
            root = f"{letter}:\\"
            if not os.path.exists(root):
                continue
            label = ""
            total = used = free = None
            try:
                usage = shutil.disk_usage(root)
                total, used, free = usage.total, usage.used, usage.free
            except OSError:
                total = used = free = None
            # Volume label via ctypes is optional; skip if fails
            try:
                import ctypes

                kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
                vol = ctypes.create_unicode_buffer(1024)
                fs = ctypes.create_unicode_buffer(1024)
                serial = ctypes.c_uint()
                max_comp = ctypes.c_uint()
                flags = ctypes.c_uint()
                if kernel32.GetVolumeInformationW(
                    root,
                    vol,
                    ctypes.sizeof(vol),
                    ctypes.byref(serial),
                    ctypes.byref(max_comp),
                    ctypes.byref(flags),
                    fs,
                    ctypes.sizeof(fs),
                ):
                    label = vol.value or ""
            except Exception:  # noqa: BLE001
                label = ""

            drives.append(
                {
                    "letter": f"{letter}:",
                    # Forward slashes are safe in HTML data attributes and
                    # accepted by the scanner on Windows.
                    "path": f"{letter}:/",
                    "path_native": root,
                    "label": label,
                    "total_bytes": total,
                    "used_bytes": used,
                    "free_bytes": free,
                    "display": f"{letter}: {label}".strip()
                    if label
                    else f"{letter}:",
                }
            )
    else:
        drives.extend(_list_posix_drives())

    return drives


_SKIP_FS = frozenset(
    {
        "proc",
        "sysfs",
        "devtmpfs",
        "tmpfs",
        "cgroup",
        "cgroup2",
        "overlay",
        "squashfs",
        "autofs",
        "debugfs",
        "securityfs",
        "pstore",
        "efivarfs",
        "fusectl",
        "configfs",
        "bpf",
        "tracefs",
        "ramfs",
        "hugetlbfs",
        "mqueue",
        "devpts",
        "rpc_pipefs",
        "binfmt_misc",
        "nsfs",
        "fuse.portal",
    }
)
_SKIP_PREFIX = ("/proc", "/sys", "/dev", "/run", "/snap", "/boot")


def _posix_drive_row(path: Path) -> dict[str, Any] | None:
    if not path.is_dir():
        return None
    try:
        usage = shutil.disk_usage(path)
        total, used, free = usage.total, usage.used, usage.free
    except OSError:
        total = used = free = None
    loc = str(path)
    return {
        "letter": loc,
        "path": loc,
        "path_native": loc,
        "label": path.name or loc,
        "total_bytes": total,
        "used_bytes": used,
        "free_bytes": free,
        "display": loc,
    }


def _list_posix_drives() -> list[dict[str, Any]]:
    seen: set[str] = set()
    drives: list[dict[str, Any]] = []

    def add(path: Path) -> None:
        try:
            key = str(path.resolve())
        except OSError:
            key = str(path)
        if key in seen:
            return
        row = _posix_drive_row(path)
        if not row:
            return
        seen.add(key)
        drives.append(row)

    mounts = Path("/proc/self/mounts")
    if mounts.is_file():
        try:
            lines = mounts.read_text(errors="replace").splitlines()
        except OSError:
            lines = []
        for line in lines:
            parts = line.split()
            if len(parts) < 3:
                continue
            dest = parts[1].replace("\\040", " ")
            fstype = parts[2].lower()
            if fstype in _SKIP_FS:
                continue
            if dest.startswith(_SKIP_PREFIX):
                continue
            add(Path(dest))
    for base in (Path("/mnt"), Path("/media"), Path("/Volumes"), Path.home()):
        add(base)
        if base in (Path("/mnt"), Path("/media"), Path("/Volumes")) and base.is_dir():
            try:
                for child in sorted(base.iterdir()):
                    if child.is_dir():
                        add(child)
            except OSError:
                pass
    add(Path("/"))
    return drives


def _ffprobe_tools_dir() -> Path:
    return ROOT / "tools" / "ffmpeg"


def _bundled_ffprobe() -> Path:
    name = "ffprobe.exe" if platform.system() == "Windows" else "ffprobe"
    return _ffprobe_tools_dir() / name


def find_ffprobe() -> str | None:
    global _FFPROBE_PATH
    if _FFPROBE_PATH and Path(_FFPROBE_PATH).is_file():
        return _FFPROBE_PATH
    found = shutil.which("ffprobe") or shutil.which("ffprobe.exe")
    if found:
        _FFPROBE_PATH = found
        return found
    portable = _bundled_ffprobe()
    if portable.is_file():
        _FFPROBE_PATH = str(portable)
        return str(portable)
    return None


def _ffprobe_runs(path: Path) -> bool:
    try:
        proc = subprocess.run(
            [str(path), "-version"],
            capture_output=True,
            text=True,
            timeout=12,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    blob = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode == 0 and "ffprobe" in blob.lower()


def _download_file(url: str, dest: Path, timeout: float = 180.0) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = Request(url, headers={"User-Agent": _FFPROBE_UA})
    with urlopen(req, timeout=timeout) as resp, dest.open("wb") as fh:
        shutil.copyfileobj(resp, fh)
    if dest.stat().st_size < 200_000:
        raise RuntimeError(f"download too small from {url}")


def install_ffprobe(force: bool = False) -> dict[str, Any]:
    """Download a portable ffmpeg essentials build next to the agent if needed."""
    existing = find_ffprobe()
    if existing and not force:
        return {
            "ok": True,
            "installed": False,
            "path": existing,
            "source": "existing",
            "detail": "ffprobe already present on this file host",
        }

    dest = _bundled_ffprobe()
    last_err = ""
    with _FFPROBE_LOCK:
        existing = find_ffprobe()
        if existing and not force:
            return {
                "ok": True,
                "installed": False,
                "path": existing,
                "source": "existing",
                "detail": "ffprobe already present on this file host",
            }
        with tempfile.TemporaryDirectory(prefix="agent-ffprobe-") as tmp:
            tmp_path = Path(tmp)
            for url in _ffprobe_urls():
                archive = tmp_path / (
                    "pack.tar.xz" if url.endswith(".tar.xz") else "pack.zip"
                )
                try:
                    _download_file(url, archive)
                    extract_to = tmp_path / "out"
                    extract_to.mkdir(parents=True, exist_ok=True)
                    if archive.suffixes[-2:] == [".tar", ".xz"] or archive.name.endswith(".tar.xz"):
                        with tarfile.open(archive) as tf:
                            tf.extractall(extract_to)
                    else:
                        with zipfile.ZipFile(archive) as zf:
                            zf.extractall(extract_to)
                    matches = list(extract_to.rglob(dest.name))
                    if not matches:
                        raise RuntimeError("archive had no ffprobe")
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(matches[0], dest)
                    dest.chmod(dest.stat().st_mode | stat.S_IXUSR)
                    for sib in matches[0].parent.glob("*.dll"):
                        shutil.copy2(sib, dest.parent / sib.name)
                    if not _ffprobe_runs(dest):
                        raise RuntimeError("extracted ffprobe did not run")
                    global _FFPROBE_PATH
                    _FFPROBE_PATH = str(dest)
                    return {
                        "ok": True,
                        "installed": True,
                        "path": str(dest),
                        "source": "portable",
                        "detail": f"installed portable ffprobe from {url}",
                    }
                except Exception as exc:  # noqa: BLE001
                    last_err = f"{url}: {exc}"
                    continue
    return {
        "ok": False,
        "installed": False,
        "path": "",
        "source": "none",
        "detail": last_err or "could not install ffprobe",
    }


def ensure_ffprobe(force: bool = False) -> str:
    report = install_ffprobe(force=force)
    if not report.get("ok") or not report.get("path"):
        raise RuntimeError(report.get("detail") or "ffprobe install failed")
    return str(report["path"])


def delete_media_file(path_str: str) -> dict[str, Any]:
    """Unlink one media file. Directories and non-media paths are refused."""
    path = normalize_scan_path(path_str)
    out: dict[str, Any] = {"ok": False, "path": str(path), "deleted": False}
    if path.is_dir():
        out["error"] = "refusing to delete a directory"
        return out
    if not path.exists():
        out["ok"] = True
        out["already_gone"] = True
        out["error"] = ""
        return out
    if not path.is_file():
        out["error"] = "not a file"
        return out
    if path.suffix.lower() not in MEDIA_EXTENSIONS:
        out["error"] = f"refusing to delete non-media file ({path.suffix or 'no extension'})"
        return out
    try:
        path.unlink()
    except OSError as exc:
        out["error"] = str(exc)
        return out
    out["ok"] = True
    out["deleted"] = True
    return out


def path_info(path_str: str) -> dict[str, Any]:
    path = normalize_scan_path(path_str)
    exists = path.exists()
    is_dir = path.is_dir() if exists else False
    return {
        "path": str(path),
        "exists": exists,
        "is_dir": is_dir,
        "readable": os.access(str(path), os.R_OK) if exists else False,
    }


def _probe_one(path_str: str, timeout: float = 40.0) -> dict[str, Any]:
    """ffprobe a single file; used by MultiMedia.Comparator deep scan."""
    path = normalize_scan_path(path_str)
    out: dict[str, Any] = {
        "ok": False,
        "tool": "ffprobe",
        "path": str(path),
        "error": "",
    }
    if not path.is_file():
        out["error"] = "not a file"
        out["tool"] = "agent"
        return out
    try:
        exe = ensure_ffprobe(force=False)
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"ffprobe missing and install failed: {exc}"
        out["tool"] = "none"
        return out
    cmd = [
        exe,
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        out["error"] = "ffprobe timed out"
        return out
    except OSError as exc:
        out["error"] = str(exc)
        return out
    if proc.returncode != 0:
        out["error"] = (proc.stderr or "ffprobe failed").strip()[:400]
        return out
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        out["error"] = f"bad json: {exc}"
        return out
    fmt = data.get("format") or {}
    videos = []
    audios = []
    for s in data.get("streams") or []:
        entry = {
            "index": s.get("index"),
            "codec_type": s.get("codec_type"),
            "codec_name": s.get("codec_name"),
            "codec_long": s.get("codec_long_name"),
            "width": s.get("width"),
            "height": s.get("height"),
            "pix_fmt": s.get("pix_fmt"),
            "profile": s.get("profile"),
            "bit_rate": s.get("bit_rate"),
            "channels": s.get("channels"),
            "channel_layout": s.get("channel_layout"),
            "sample_rate": s.get("sample_rate"),
            "bits_per_raw_sample": s.get("bits_per_raw_sample"),
            "r_frame_rate": s.get("r_frame_rate"),
            "color_transfer": s.get("color_transfer"),
            "color_primaries": s.get("color_primaries"),
            "color_space": s.get("color_space"),
            "field_order": s.get("field_order"),
            "tags": s.get("tags") or {},
            "side_data_list": s.get("side_data_list") or [],
        }
        ctype = s.get("codec_type")
        if ctype == "video" and (s.get("codec_name") or "") not in {"mjpeg", "png"}:
            videos.append(entry)
        elif ctype == "audio":
            audios.append(entry)
    out.update(
        {
            "ok": True,
            "duration_s": float(fmt["duration"]) if fmt.get("duration") else None,
            "size_bytes": int(fmt["size"]) if fmt.get("size") else path.stat().st_size,
            "bit_rate": int(fmt["bit_rate"]) if str(fmt.get("bit_rate") or "").isdigit() else None,
            "format_name": fmt.get("format_name"),
            "format_long": fmt.get("format_long_name"),
            "video": videos[0] if videos else None,
            "audio": audios[0] if audios else None,
            "videos": videos,
            "audios": audios,
        }
    )
    return out


def probe_paths(paths: list[str], limit: int = 12) -> list[dict[str, Any]]:
    results = []
    for raw in paths[:limit]:
        if not raw:
            continue
        results.append(_probe_one(str(raw)))
    return results


class AgentHandler(BaseHTTPRequestHandler):
    server_version = "MediaCatalogAgent/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _check_token(self) -> bool:
        expected = AGENT_TOKEN
        if not expected:
            return True
        got = self.headers.get("X-Agent-Token", "")
        return got == expected

    def _send_json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Agent-Token")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON body: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError("JSON body must be an object")
        return data

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Agent-Token")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        if not self._check_token():
            self._send_json(401, {"error": "Invalid or missing X-Agent-Token"})
            return
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        try:
            if path == "/api/health":
                self._send_json(
                    200,
                    {
                        "ok": True,
                        "service": "media-catalog-agent",
                        "platform": platform.system(),
                        "hostname": platform.node(),
                        "python": platform.python_version(),
                        "version": AGENT_VERSION,
                        "features": [
                            "scan",
                            "drives",
                            "smart",
                            "crystaldiskinfo",
                            "probe",
                            "ffprobe-install",
                            "delete",
                        ],
                        "ffprobe": bool(find_ffprobe()),
                        "ffprobe_path": find_ffprobe() or "",
                    },
                )
                return
            if path == "/api/drives":
                self._send_json(200, {"drives": list_local_drives()})
                return
            if path == "/api/smart":
                qs = parse_qs(parsed.query)
                target = (qs.get("path") or [""])[0].strip()
                force = (qs.get("force") or ["0"])[0] in {"1", "true", "yes"}
                if not target:
                    smap = (
                        windows_smart_map(force=force)
                        if platform.system() == "Windows"
                        else {}
                    )
                    cdi_ok = False
                    cdi_err = ""
                    try:
                        from crystaldisk import find_crystaldisk_exe, get_crystaldisk_drives

                        cdi_ok = bool(find_crystaldisk_exe())
                        if cdi_ok and force:
                            get_crystaldisk_drives(force=True)
                    except Exception as exc:  # noqa: BLE001
                        cdi_err = str(exc)
                    self._send_json(
                        200,
                        {
                            "drives": smap,
                            "source": "batch",
                            "version": AGENT_VERSION,
                            "crystaldiskinfo": cdi_ok,
                            "crystaldiskinfo_error": cdi_err,
                        },
                    )
                    return
                if force:
                    windows_smart_map(force=True)
                    try:
                        from crystaldisk import get_crystaldisk_drives

                        get_crystaldisk_drives(force=True)
                    except Exception:  # noqa: BLE001
                        pass
                self._send_json(200, smart_for_path(target))
                return
            if path == "/api/smart/crystaldisk":
                # Full CrystalDiskInfo dump (all disks)
                try:
                    from crystaldisk import (
                        find_crystaldisk_exe,
                        get_crystaldisk_drives,
                    )

                    exe = find_crystaldisk_exe()
                    if not exe:
                        self._send_json(
                            404,
                            {
                                "error": "CrystalDiskInfo not installed",
                                "hint": "https://crystalmark.info/en/software/crystaldiskinfo/",
                            },
                        )
                        return
                    force = (parse_qs(parsed.query).get("force") or ["1"])[0] in {
                        "1",
                        "true",
                        "yes",
                    }
                    drives, err = get_crystaldisk_drives(force=force)
                    self._send_json(
                        200,
                        {
                            "ok": not err,
                            "exe": str(exe),
                            "error": err,
                            "count": len(drives),
                            "drives": drives,
                            "source": "crystaldiskinfo",
                            "version": AGENT_VERSION,
                        },
                    )
                except Exception as exc:  # noqa: BLE001
                    self._send_json(500, {"error": str(exc)})
                return
            if path == "/api/ffprobe":
                found = find_ffprobe()
                self._send_json(
                    200,
                    {
                        "ok": bool(found),
                        "path": found or "",
                        "installed": False,
                        "source": "existing" if found else "none",
                        "version": AGENT_VERSION,
                    },
                )
                return
            if path == "/api/path":
                qs = parse_qs(parsed.query)
                target = (qs.get("path") or [""])[0]
                if not target:
                    self._send_json(400, {"error": "path query required"})
                    return
                self._send_json(200, path_info(target))
                return
            self._send_json(404, {"error": f"Unknown path {path}"})
        except Exception as exc:  # noqa: BLE001
            self._send_json(
                500, {"error": str(exc), "trace": traceback.format_exc()}
            )

    def do_POST(self) -> None:  # noqa: N802
        if not self._check_token():
            self._send_json(401, {"error": "Invalid or missing X-Agent-Token"})
            return
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        try:
            if path == "/api/scan":
                body = self._read_json()
                target = (body.get("path") or "").strip()
                if not target:
                    self._send_json(400, {"error": "path is required"})
                    return
                info = path_info(target)
                if not info["exists"] or not info["is_dir"]:
                    self._send_json(
                        400,
                        {
                            "error": (
                                f"Path is not a directory: {target!r} "
                                f"(normalized: {info.get('path')!r}). "
                                "Use e.g. D:/ or D:/Movies — a bare letter "
                                "like D: is not enough on Windows."
                            ),
                            "path_info": info,
                        },
                    )
                    return
                # Large multi-TB trees can take a long time; keep connection open
                items = scan_root(target)
                self._send_json(
                    200,
                    {
                        "path": info["path"],
                        "count": len(items),
                        "items": items,
                    },
                )
                return
            if path == "/api/ffprobe":
                body = self._read_json()
                force = bool(body.get("force"))
                report = install_ffprobe(force=force)
                status = 200 if report.get("ok") else 500
                report["version"] = AGENT_VERSION
                self._send_json(status, report)
                return
            if path == "/api/probe":
                body = self._read_json()
                paths = body.get("paths") or []
                single = (body.get("path") or "").strip()
                if single:
                    paths = [single] + list(paths)
                if not paths:
                    self._send_json(400, {"error": "path or paths required"})
                    return
                cleaned = [str(p).strip() for p in paths if str(p).strip()]
                results = probe_paths(cleaned)
                self._send_json(
                    200,
                    {
                        "ok": True,
                        "count": len(results),
                        "results": results,
                        "version": AGENT_VERSION,
                    },
                )
                return
            if path == "/api/delete":
                body = self._read_json()
                target = (body.get("path") or "").strip()
                if not target:
                    self._send_json(400, {"error": "path is required", "ok": False})
                    return
                report = delete_media_file(target)
                status = 200 if report.get("ok") else 400
                report["version"] = AGENT_VERSION
                self._send_json(status, report)
                return
            self._send_json(404, {"error": f"Unknown path {path}"})
        except FileNotFoundError as exc:
            self._send_json(400, {"error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            self._send_json(
                500, {"error": str(exc), "trace": traceback.format_exc()}
            )


def main() -> None:
    global AGENT_TOKEN

    parser = argparse.ArgumentParser(description="Media Catalog file-host agent")
    parser.add_argument("--host", default=AGENT_HOST, help="Bind address (default 0.0.0.0)")
    parser.add_argument("--port", type=int, default=AGENT_PORT, help="Port (default 8766)")
    parser.add_argument(
        "--token",
        default=AGENT_TOKEN,
        help="Optional shared secret (also MEDIA_CATALOG_AGENT_TOKEN)",
    )
    args = parser.parse_args()
    AGENT_TOKEN = args.token or ""

    httpd = ThreadingHTTPServer((args.host, args.port), AgentHandler)
    print(f"Media Catalog agent on http://{args.host}:{args.port}")
    print(f"Platform: {platform.system()} ({platform.node()})")
    if AGENT_TOKEN:
        print("Token auth: enabled (send X-Agent-Token)")
    else:
        print("Token auth: disabled (LAN only recommended)")
    print(
        "Endpoints: /api/health  /api/drives  /api/scan  /api/path  "
        "/api/smart  /api/probe  /api/ffprobe  /api/delete"
    )
    print("Press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping.")
        httpd.server_close()


if __name__ == "__main__":
    main()
