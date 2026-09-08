"""
CrystalDiskInfo integration (Windows).

CrystalDiskInfo is free software from Crystal Dew World:
  https://crystalmark.info/en/software/crystaldiskinfo/

We invoke DiskInfo64.exe /CopyExit (or DiskInfoA64 / DiskInfo32) to produce
DiskInfo.txt, then parse health, temperature, model, letters, and SMART
attributes (including reallocated/pending sector counts).

This does not redistribute CrystalDiskInfo binaries — user installs it
separately. We only call the installed app and parse its text export.
"""

from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

# Attribute ID (hex or decimal as CDI prints) → our field
_ATTR_FIELD = {
    "05": "sector_reallocated",
    "5": "sector_reallocated",
    "c5": "sector_pending",  # sometimes hex in older dumps
    "197": "sector_pending",
    "c6": "sector_uncorrectable",
    "198": "sector_uncorrectable",
    "c7": "sector_crc",
    "199": "sector_crc",
    "bb": "sector_reported_uncorrect",
    "187": "sector_reported_uncorrect",
}

_ATTR_NAME_FIELD = {
    "reallocated sectors count": "sector_reallocated",
    "reallocated sector count": "sector_reallocated",
    "reallocated_sector_ct": "sector_reallocated",
    "current pending sector count": "sector_pending",
    "current_pending_sector": "sector_pending",
    "offline uncorrectable": "sector_uncorrectable",
    "offline_uncorrectable": "sector_uncorrectable",
    "udma crc error count": "sector_crc",
    "ultra dma crc error count": "sector_crc",
    "reported uncorrectable errors": "sector_reported_uncorrect",
    "reported_uncorrect": "sector_reported_uncorrect",
}


def find_crystaldisk_exe() -> Path | None:
    """Locate DiskInfo*.exe on a typical Windows install."""
    env = os.environ.get("CRYSTALDISKINFO_PATH", "").strip()
    if env:
        p = Path(env)
        if p.is_file():
            return p
        for name in ("DiskInfo64.exe", "DiskInfoA64.exe", "DiskInfo32.exe", "DiskInfo.exe"):
            cand = p / name
            if cand.is_file():
                return cand

    candidates: list[Path] = []
    for base in (
        os.environ.get("ProgramFiles", r"C:\Program Files"),
        os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
        os.environ.get("LOCALAPPDATA", ""),
        str(Path.home() / "AppData" / "Local"),
    ):
        if not base:
            continue
        root = Path(base)
        for folder in (
            root / "CrystalDiskInfo",
            root / "CrystalDiskInfo8",
            root / "CrystalDiskInfo9",
        ):
            for name in (
                "DiskInfo64.exe",
                "DiskInfoA64.exe",
                "DiskInfo32.exe",
                "DiskInfo.exe",
            ):
                candidates.append(folder / name)

    # Portable next to agent, or tools/ dropped by the 1.5 installer
    here = Path(__file__).resolve().parent
    for name in ("DiskInfo64.exe", "DiskInfoA64.exe", "DiskInfo.exe"):
        candidates.append(here / "CrystalDiskInfo" / name)
        candidates.append(here / "tools" / "CrystalDiskInfo" / name)
        candidates.append(here / name)

    for c in candidates:
        if c.is_file():
            return c
    return None


def _diskinfo_candidates(exe: Path) -> list[Path]:
    """Places CrystalDiskInfo may write DiskInfo.txt."""
    homes = []
    try:
        homes.append(Path.home())
    except Exception:  # noqa: BLE001
        pass
    return [
        exe.parent / "DiskInfo.txt",
        Path.cwd() / "DiskInfo.txt",
        *([h / "DiskInfo.txt" for h in homes]),
        Path(os.environ.get("USERPROFILE", "")) / "DiskInfo.txt",
        Path(os.environ.get("TEMP", "")) / "DiskInfo.txt",
    ]


def _newest_diskinfo(exe: Path, max_age_sec: float = 86400.0) -> Path | None:
    """Return newest existing DiskInfo.txt under max_age_sec, or any if max_age is 0."""
    newest: Path | None = None
    newest_mtime = 0.0
    now = time.time()
    for p in _diskinfo_candidates(exe):
        try:
            if not p.is_file() or p.stat().st_size < 50:
                continue
            mtime = p.stat().st_mtime
            if max_age_sec and (now - mtime) > max_age_sec:
                continue
            if mtime >= newest_mtime:
                newest = p
                newest_mtime = mtime
        except OSError:
            continue
    return newest


def run_crystaldisk_export(
    exe: Path | None = None,
    timeout: float = 120.0,
) -> tuple[Path | None, str]:
    """
    Run CrystalDiskInfo /CopyExit and return (path_to_DiskInfo.txt, error).

    Note: DiskInfo64.exe often requires Administrator (WinError 740).
    If launch fails with elevation error, we fall back to a recent DiskInfo.txt
    (user can open CrystalDiskInfo once as Admin, or run our agent as Admin).
    """
    exe = exe or find_crystaldisk_exe()
    if not exe:
        return None, (
            "CrystalDiskInfo not found. Install from "
            "https://crystalmark.info/en/software/crystaldiskinfo/ "
            "or set CRYSTALDISKINFO_PATH to the install folder."
        )

    out_txt = exe.parent / "DiskInfo.txt"
    # Snapshot mtime so we can detect a successful rewrite
    prev_mtime = out_txt.stat().st_mtime if out_txt.is_file() else 0.0

    launch_err = ""
    proc = None
    try:
        # Prefer working directory = install dir so DiskInfo.txt lands there
        creation = 0
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            creation = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
        proc = subprocess.run(
            [str(exe), "/CopyExit"],
            cwd=str(exe.parent),
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=creation,
        )
    except subprocess.TimeoutExpired:
        launch_err = f"CrystalDiskInfo timed out after {timeout}s"
    except OSError as exc:
        # WinError 740 = requires elevation
        winerr = getattr(exc, "winerror", None)
        if winerr == 740:
            launch_err = (
                "CrystalDiskInfo requires Administrator. "
                "Right-click RUN_AGENT.bat → Run as administrator "
                "(or open CrystalDiskInfo once as Admin so DiskInfo.txt refreshes)."
            )
        else:
            launch_err = f"Failed to launch CrystalDiskInfo: {exc}"

    # Wait for file write after successful launch
    if not launch_err:
        for _ in range(30):
            try:
                if out_txt.is_file() and out_txt.stat().st_size > 50:
                    if out_txt.stat().st_mtime >= prev_mtime:
                        return out_txt, ""
            except OSError:
                pass
            time.sleep(0.2)

    # Elevation failure or no new file: use recent cached export if present
    cached = _newest_diskinfo(exe, max_age_sec=7 * 86400.0)
    if cached:
        age_h = (time.time() - cached.stat().st_mtime) / 3600.0
        note = launch_err or "DiskInfo.txt not refreshed"
        return cached, (
            f"Using cached {cached.name} ({age_h:.1f}h old). {note}"
        )

    if launch_err:
        return None, launch_err
    err = ""
    if proc is not None:
        err = (proc.stderr or proc.stdout or "").strip()
    return None, (
        f"DiskInfo.txt not produced by {exe.name}. "
        f"Exit={getattr(proc, 'returncode', '?')}. {err[:200]}"
    )


def _raw_int(raw: str) -> int | None:
    """Parse CDI RawValues — usually 12 hex digits; count is typically low bytes."""
    raw = (raw or "").strip().replace(",", "").replace(" ", "")
    if not raw or raw == "-":
        return None
    # 12-digit hex raw (CrystalDiskInfo default)
    if re.fullmatch(r"[0-9a-fA-F]{8,16}", raw):
        try:
            # Use full value; for sector counts CDI puts count in low bytes
            val = int(raw, 16)
            # If high bytes dominate (vendor specific), still take low 32 bits
            if val > 0xFFFFFFFF:
                low = val & 0xFFFFFFFF
                # Prefer low if it looks like a counter
                if low < 1_000_000:
                    return low
            return val
        except ValueError:
            pass
    m = re.search(r"(\d+)", raw)
    return int(m.group(1)) if m else None


def parse_diskinfo_txt(text: str) -> list[dict[str, Any]]:
    """
    Parse CrystalDiskInfo DiskInfo.txt into a list of drive dicts.
    Each dict is ready to merge into our SMART report format.
    """
    # Split into per-disk sections: lines starting with " (" digit or "Model :"
    # CDI separates disks with long dashes and a header like " (1) ModelName"
    chunks: list[str] = []
    current: list[str] = []
    header_re = re.compile(r"^\s*\(\d+\)\s+")

    for line in text.splitlines():
        if header_re.match(line) and current:
            chunks.append("\n".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        chunks.append("\n".join(current))

    # If no (n) headers, try split on "Model :"
    if len(chunks) <= 1 and text.count("Model :") + text.count("Model:") >= 1:
        parts = re.split(r"(?=^\s*Model\s*:)", text, flags=re.M | re.I)
        chunks = [p for p in parts if re.search(r"Model\s*:", p, re.I)]

    drives: list[dict[str, Any]] = []
    for chunk in chunks:
        d = _parse_one_disk_chunk(chunk)
        if d and (d.get("model") or d.get("serial") or d.get("letters")):
            drives.append(d)
    return drives


def _parse_one_disk_chunk(chunk: str) -> dict[str, Any] | None:
    def field(*names: str) -> str:
        for n in names:
            m = re.search(
                rf"^\s*{re.escape(n)}\s*:\s*(.+?)\s*$",
                chunk,
                re.I | re.M,
            )
            if m:
                return m.group(1).strip()
        return ""

    model = field("Model")
    firmware = field("Firmware")
    serial = field("Serial Number", "SerialNumber")
    disk_size = field("Disk Size", "DiskSize")
    transfer = field("Transfer Mode", "Interface")
    power_hours = field("Power On Hours", "PowerOnHours")
    power_count = field("Power On Count", "PowerOnCount")
    temp_s = field("Temperature")
    health = field("Health Status", "HealthStatus")
    features = field("Features")
    letters_s = field("Drive Letter", "DriveLetter")

    # Header line: (1) Some Model
    if not model:
        hm = re.search(r"^\s*\(\d+\)\s+(.+)$", chunk, re.M)
        if hm:
            model = hm.group(1).strip()

    if not model and not serial and not letters_s:
        return None

    letters: list[str] = []
    for m in re.finditer(r"([A-Za-z]):", letters_s or ""):
        letters.append(m.group(1).upper())

    temp = None
    tm = re.search(r"(\d+)\s*C", temp_s or "", re.I)
    if tm:
        temp = int(tm.group(1))

    health_raw = health or "Unknown"
    status = _cdi_health_to_status(health_raw)

    # SMART table body
    sectors = _parse_cdi_smart_table(chunk)

    media = ""
    bus = ""
    feat_l = (features or "").lower()
    model_l = (model or "").lower()
    if "nvme" in feat_l or "nvme" in model_l or "nvme" in (transfer or "").lower():
        bus = "NVMe"
        media = "SSD"
    elif "ssd" in model_l or "solid state" in feat_l:
        media = "SSD"
    if "usb" in (transfer or "").lower() or "usb" in feat_l:
        bus = bus or "USB"
    if "sata" in (transfer or "").lower():
        bus = bus or "SATA"

    volume_label = ""
    # Sometimes CDI embeds label near letters
    return {
        "source": "crystaldiskinfo",
        "model": model,
        "firmware": firmware,
        "serial": serial,
        "disk_size": disk_size,
        "transfer_mode": transfer,
        "power_on_hours": power_hours,
        "power_on_count": power_count,
        "temperature_c": temp,
        "status_raw": health_raw,
        "status": status,
        "features": features,
        "letters": letters,
        "media": media,
        "bus": bus,
        "volume_label": volume_label,
        "sector_attrs_available": bool(sectors.get("sector_attrs_available")),
        "sector_reallocated": sectors.get("sector_reallocated"),
        "sector_pending": sectors.get("sector_pending"),
        "sector_uncorrectable": sectors.get("sector_uncorrectable"),
        "sector_crc": sectors.get("sector_crc"),
        "sector_reported_uncorrect": sectors.get("sector_reported_uncorrect"),
        "sector_summary": sectors.get("sector_summary") or "",
        "sector_attrs": sectors.get("attrs") or {},
        "ok": True,
        "detail": f"CrystalDiskInfo: {health_raw}"
        + (f" · {sectors.get('sector_summary')}" if sectors.get("sector_summary") else ""),
    }


def _cdi_health_to_status(health: str) -> str:
    h = (health or "").strip().lower()
    if h in {"good", "正常", "ok", "passed", "pass"}:
        return "healthy"
    if h in {"caution", "注意", "warning", "warn"}:
        return "warning"
    if h in {"bad", "異常", "fail", "failed", "failure", "critical"}:
        return "failing"
    if "good" in h:
        return "healthy"
    if "caution" in h or "warn" in h:
        return "warning"
    if "bad" in h or "fail" in h or "abnormal" in h:
        return "failing"
    return "unknown"


def _parse_cdi_smart_table(chunk: str) -> dict[str, Any]:
    """
    Parse CDI SMART attribute lines.

    Formats seen:
      ID Cur Wor Thr RawValues(6) Attribute Name
      05 200 200 _00 000000000000 Reallocated Sectors Count

      ID  Attribute Name ...
    """
    out: dict[str, Any] = {
        "sector_attrs_available": False,
        "attrs": {},
    }
    # Find SMART section
    smart_part = chunk
    sm = re.search(
        r"--\s*S\.?M\.?A\.?R\.?T\.?\s*-+(.*)$",
        chunk,
        re.I | re.S,
    )
    if sm:
        smart_part = sm.group(1)

    # Classic CDI line:
    # ID Cur Wor Thr RawValues(6) Attribute Name
    # 05 _00 200 200 000000000003 Reallocated Sectors Count
    # or
    # 05 200 200 _50 000000000003 Reallocated Sectors Count
    line_re = re.compile(
        r"^\s*([0-9A-Fa-f]{2})\s+"
        r"(\S+)\s+(\S+)\s+(\S+)\s+"
        r"([0-9A-Fa-f]{8,16})\s+"
        r"(.+?)\s*$",
        re.M,
    )
    for m in line_re.finditer(smart_part):
        attr_id = m.group(1).lower()
        raw = m.group(5)
        name = m.group(6).strip()
        val = _raw_int(raw)
        field = _ATTR_FIELD.get(attr_id) or _ATTR_FIELD.get(attr_id.lstrip("0") or "0")
        if not field:
            field = _ATTR_NAME_FIELD.get(name.lower())
        if field and val is not None:
            out[field] = val
            out["attrs"][name] = val
            out["sector_attrs_available"] = True

    # Name + 12-hex raw anywhere in SMART section
    if not out["sector_attrs_available"]:
        for name, field in _ATTR_NAME_FIELD.items():
            m = re.search(
                rf"([0-9A-Fa-f]{{12}})\s+{re.escape(name)}",
                smart_part,
                re.I,
            )
            if not m:
                m = re.search(
                    rf"{re.escape(name)}.*?([0-9A-Fa-f]{{12}})",
                    smart_part,
                    re.I,
                )
            if m:
                val = _raw_int(m.group(1))
                if val is not None:
                    out[field] = val
                    out["sector_attrs_available"] = True

    # Build summary like smart_health.sector_risk_summary expects
    parts = []
    for key, label in (
        ("sector_pending", "Pending sectors"),
        ("sector_uncorrectable", "Offline uncorrectable"),
        ("sector_reallocated", "Reallocated sectors"),
        ("sector_reported_uncorrect", "Reported uncorrectable"),
        ("sector_crc", "UDMA CRC errors"),
    ):
        if out.get(key) is not None:
            parts.append(f"{label}: {out[key]}")
    out["sector_summary"] = "; ".join(parts)
    return out


# Cache full CDI scan for a short TTL (agent may query many letters)
_CDI_CACHE: dict[str, Any] = {"ts": 0.0, "drives": [], "error": ""}
_CDI_TTL = 45.0


def get_crystaldisk_drives(force: bool = False) -> tuple[list[dict[str, Any]], str]:
    """
    Return (list of parsed drive dicts, error_string).
    Uses short cache so multi-letter SMART checks share one /CopyExit.
    """
    import time as _time

    now = _time.time()
    if (
        not force
        and _CDI_CACHE["drives"]
        and (now - float(_CDI_CACHE["ts"])) < _CDI_TTL
    ):
        return list(_CDI_CACHE["drives"]), str(_CDI_CACHE.get("error") or "")

    path, err = run_crystaldisk_export()
    if err or not path:
        _CDI_CACHE.update({"ts": now, "drives": [], "error": err})
        return [], err

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return [], str(exc)

    drives = parse_diskinfo_txt(text)
    _CDI_CACHE.update({"ts": now, "drives": drives, "error": ""})
    return drives, ""


def match_letter(drives: list[dict[str, Any]], letter: str) -> dict[str, Any] | None:
    letter = (letter or "").strip().upper()[:1]
    if not letter:
        return None
    for d in drives:
        if letter in (d.get("letters") or []):
            return d
    # Single disk no letters — return first if only one
    if len(drives) == 1 and not drives[0].get("letters"):
        return drives[0]
    return None


def crystaldisk_report_for_letter(letter: str, force: bool = False) -> dict[str, Any]:
    """Build a SMART-style report for one drive letter via CrystalDiskInfo."""
    drives, err = get_crystaldisk_drives(force=force)
    if err and not drives:
        return {
            "ok": False,
            "source": "crystaldiskinfo",
            "status": "unknown",
            "status_raw": "Unavailable",
            "detail": err,
            "letter": letter,
            "cdi_warning": err,
        }
    match = match_letter(drives, letter)
    if not match:
        return {
            "ok": True,
            "source": "crystaldiskinfo",
            "status": "unknown",
            "status_raw": "Not listed",
            "detail": (
                f"CrystalDiskInfo has no entry for {letter}: "
                f"({len(drives)} disk(s) in report). "
                + (err or "Try Run as administrator or open CDI once.")
            ),
            "letter": letter,
            "cdi_disk_count": len(drives),
            "cdi_warning": err,
        }
    report = dict(match)
    report["letter"] = letter.upper()[:1]
    report["ok"] = True
    if err:
        report["cdi_warning"] = err
    # Escalate status from sector attrs
    try:
        from smart_health import merge_status, sector_risk_summary

        hint, summary, note = sector_risk_summary(
            {
                "sector_attrs_available": report.get("sector_attrs_available"),
                "sector_reallocated": report.get("sector_reallocated"),
                "sector_pending": report.get("sector_pending"),
                "sector_uncorrectable": report.get("sector_uncorrectable"),
                "sector_crc": report.get("sector_crc"),
                "sector_reported_uncorrect": report.get(
                    "sector_reported_uncorrect"
                ),
                "nvme_media_errors": report.get("nvme_media_errors"),
            }
        )
        report["status"] = merge_status(str(report.get("status") or "unknown"), hint)
        detail_bits = [f"CrystalDiskInfo: {report.get('status_raw')}"]
        if summary:
            report["sector_summary"] = summary
            detail_bits.append(summary)
        if note:
            detail_bits.append(note)
        if err:
            detail_bits.append(err)
        report["detail"] = " · ".join(detail_bits)
    except Exception:  # noqa: BLE001
        pass
    return report
