"""S.M.A.R.T. / disk health helpers (local Linux + normalized agent payloads)."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

# Drive tags applied automatically from health checks
SMART_TAG_PREFIX = "SMART:"
SMART_TAGS = {
    "healthy": "SMART:Healthy",
    "warning": "SMART:Warning",
    "failing": "SMART:Failing",
    "unknown": "SMART:Unknown",
}


def normalize_status(raw: str | None) -> str:
    """Map vendor strings → healthy | warning | failing | unknown."""
    if not raw:
        return "unknown"
    s = str(raw).strip().lower()
    if s in {"healthy", "ok", "passed", "good", "pass"}:
        return "healthy"
    if s in {
        "warning",
        "caution",
        "degraded",
        "predictive failure",
        "pred fail",
        "pre-fail",
    }:
        return "warning"
    if s in {
        "failing",
        "failed",
        "failure",
        "unhealthy",
        "critical",
        "bad",
        "error",
    }:
        return "failing"
    if "pass" in s or s == "ok":
        return "healthy"
    if "fail" in s or "unhealth" in s or "critical" in s:
        return "failing"
    if "warn" in s or "degrad" in s or "caution" in s:
        return "warning"
    return "unknown"


def status_label(status: str) -> str:
    return {
        "healthy": "Healthy",
        "warning": "Warning",
        "failing": "Failing",
        "unknown": "Unknown",
    }.get(status, "Unknown")


def smart_tag_for(status: str) -> str:
    return SMART_TAGS.get(normalize_status(status), SMART_TAGS["unknown"])


def empty_report(**extra: Any) -> dict[str, Any]:
    base = {
        "status": "unknown",
        "status_raw": "",
        "temperature_c": None,
        "model": "",
        "serial": "",
        "media": "",
        "bus": "",
        "drive_type": "",
        "source": "",
        "detail": "",
        "ok": False,
        "hardware_type": "unknown",
        "hardware_label": "Unknown",
        # Bad-sector related SMART (None = not available from this probe)
        "sector_attrs_available": False,
        "sector_reallocated": None,
        "sector_pending": None,
        "sector_uncorrectable": None,
        "sector_crc": None,
        "sector_reported_uncorrect": None,
        "nvme_media_errors": None,
        "sector_summary": "",
    }
    base.update(extra)
    return base


# hardware_type codes used in UI CSS
HARDWARE_LABELS = {
    "ssd": "SSD",
    "nvme": "NVMe SSD",
    "internal_hdd": "Internal HDD",
    "portable": "Portable",
    "portable_ssd": "Portable SSD",
    "portable_hdd": "Portable HDD",
    "network": "Network",
    "optical": "Optical",
    "unknown": "Unknown",
}


def hardware_label(code: str | None) -> str:
    return HARDWARE_LABELS.get((code or "unknown").lower(), "Unknown")


# Product / product-line icons (stylized shapes — not trademark logos)
PRODUCT_LABELS = {
    "elements": "WD Elements",
    "my_book": "WD My Book",
    "passport": "WD Passport",
    "easystore": "WD easystore",
    "expansion": "Seagate Expansion",
    "backup_plus": "Seagate Backup+",
    "one_touch": "Seagate One Touch",
    "canvio": "Toshiba Canvio",
    "g_drive": "G-Drive",
    "lacie": "LaCie",
    "portable_generic": "Portable drive",
    "desktop_external": "Desktop external",
    "internal": "Internal drive",
    "ssd_stick": "SSD",
    "nvme": "NVMe SSD",
    "network": "Network / NAS",
    "unknown": "Drive",
}


def product_label(code: str | None) -> str:
    return PRODUCT_LABELS.get((code or "unknown").lower(), "Drive")


def detect_drive_product(
    *,
    name: str = "",
    model: str = "",
    volume_label: str = "",
    root_path: str = "",
    media: str = "",
    bus: str = "",
    hardware_type: str = "",
) -> tuple[str, str]:
    """
    Detect consumer portable product line for icon selection.
    Returns (product_id, product_label).
    """
    blob = " ".join(
        [
            (name or "").lower(),
            (model or "").lower(),
            (volume_label or "").lower(),
            (root_path or "").lower(),
            (media or "").lower(),
            (bus or "").lower(),
        ]
    )
    hw = (hardware_type or "").lower()

    # Specific product lines (order matters — more specific first)
    rules: list[tuple[tuple[str, ...], str]] = (
        (("my book", "mybook"), "my_book"),
        (("my passport", "passport"), "passport"),
        (("elements",), "elements"),
        (("easystore", "easy store"), "easystore"),
        (("backup plus", "backup+", "backup plus hub"), "backup_plus"),
        (("one touch", "onetouch"), "one_touch"),
        (("expansion",), "expansion"),
        (("canvio",), "canvio"),
        (("g-drive", "gdrive", "g drive"), "g_drive"),
        (("lacie",), "lacie"),
    )
    for needles, pid in rules:
        if any(n in blob for n in needles):
            return pid, PRODUCT_LABELS[pid]

    # Form-factor fallbacks for icon set
    if hw in {"network"} or "nas" in blob:
        return "network", PRODUCT_LABELS["network"]
    if hw in {"nvme"} or "nvme" in blob:
        return "nvme", PRODUCT_LABELS["nvme"]
    if hw in {"ssd", "portable_ssd"} or ("ssd" in blob and "hdd" not in blob):
        return "ssd_stick", PRODUCT_LABELS["ssd_stick"]
    if hw in {"internal_hdd"}:
        return "internal", PRODUCT_LABELS["internal"]
    if hw in {"portable", "portable_hdd"}:
        # Desktop-class externals vs pocket portables — size heuristic from name
        if any(x in blob for x in ("8tb", "10tb", "12tb", "14tb", "16tb", "18tb", "20tb", "22tb")):
            return "desktop_external", PRODUCT_LABELS["desktop_external"]
        return "portable_generic", PRODUCT_LABELS["portable_generic"]

    return "unknown", PRODUCT_LABELS["unknown"]


# Volume / product names that almost always mean external USB enclosures
_PORTABLE_NAME_HINTS = (
    "elements",
    "my book",
    "my passport",
    "passport",
    "expansion",
    "easystore",
    "backup plus",
    "portable",
    "external",
    "usb",
    "seagate",
    "toshiba canvio",
    "canvio",
    "wd my",
    "g-drive",
    "gdrive",
)
_SSD_NAME_HINTS = ("ssd", "nvme", "solid state", "m.2", "m2 ")
_NAS_NAME_HINTS = ("nas", "network", "smb", "cifs", "nfs")


def classify_drive_hardware(
    *,
    media: str = "",
    bus: str = "",
    drive_type: str = "",
    model: str = "",
    detail: str = "",
    device: str = "",
    name: str = "",
    root_path: str = "",
) -> tuple[str, str]:
    """
    Classify storage form-factor for UI.

    Returns (hardware_type, hardware_label).
    Types: nvme, ssd, internal_hdd, portable_ssd, portable_hdd, portable,
           network, optical, unknown
    """
    media_l = (media or "").strip().lower()
    bus_l = (bus or "").strip().lower()
    dtype_l = (drive_type or "").strip().lower()
    model_l = (model or "").strip().lower()
    detail_l = (detail or "").strip().lower()
    device_l = (device or "").strip().lower()
    name_l = (name or "").strip().lower()
    path_l = (root_path or "").strip().lower().replace("\\", "/")
    blob = " ".join(
        [media_l, bus_l, dtype_l, model_l, detail_l, device_l, name_l, path_l]
    )

    # Network / optical first
    if (
        "network" in dtype_l
        or "network" in detail_l
        or any(h in blob for h in _NAS_NAME_HINTS)
        or bus_l in {"file back end", "filebackend"}
        or path_l.startswith("//")
        or path_l.startswith("smb:")
    ):
        return "network", HARDWARE_LABELS["network"]
    if "cd" in dtype_l or "dvd" in dtype_l or "optical" in media_l or bus_l == "atapi":
        return "optical", HARDWARE_LABELS["optical"]

    # Solid-state signals
    is_nvme = (
        "nvme" in bus_l
        or "nvme" in media_l
        or "nvme" in device_l
        or "nvme" in model_l
        or "nvme" in name_l
    )
    is_ssd = is_nvme or media_l in {
        "ssd",
        "solid state drive",
        "solid-state",
    } or "ssd" in media_l or (
        "ssd" in model_l and "hdd" not in model_l
    ) or any(h in name_l or h in model_l for h in _SSD_NAME_HINTS)

    # Rotational / HDD
    is_hdd = media_l in {"hdd", "hard disk drive", "disk"} or (
        "hdd" in media_l and "ssd" not in media_l
    )
    if "rota" in blob and "0" in blob:
        is_ssd = True

    # Portable / external bus or product name
    is_portable = bus_l in {
        "usb",
        "usb2",
        "usb3",
        "uas",
        "1394",
        "firewire",
        "sd",
        "mmc",
        "thunderbolt",
    } or "usb" in bus_l or "external" in bus_l or "portable" in model_l
    if dtype_l in {"removable"} or "removable" in dtype_l:
        is_portable = True
    if "usb" in detail_l or "enclosure" in detail_l:
        is_portable = True
    if any(h in name_l or h in model_l or h in path_l for h in _PORTABLE_NAME_HINTS):
        is_portable = True
        # Consumer multi-TB USB drives are almost always spinning HDD unless named SSD
        if not is_ssd:
            is_hdd = True

    # Bare Windows C: with no other signals → treat as internal
    letter_only = bool(re.match(r"^[a-z]:/?$", path_l))
    if letter_only and path_l.startswith("c") and not is_portable:
        if is_ssd or is_nvme:
            pass
        else:
            is_hdd = is_hdd or True  # default internal disk assumption

    if is_nvme and not is_portable:
        return "nvme", HARDWARE_LABELS["nvme"]
    if is_ssd and is_portable:
        return "portable_ssd", HARDWARE_LABELS["portable_ssd"]
    if is_ssd:
        return "ssd", HARDWARE_LABELS["ssd"]
    if is_hdd and is_portable:
        return "portable_hdd", HARDWARE_LABELS["portable_hdd"]
    if is_portable:
        return "portable", HARDWARE_LABELS["portable"]
    if is_hdd or bus_l in {"sata", "sas", "ata", "ide", "scsi", "raid"}:
        return "internal_hdd", HARDWARE_LABELS["internal_hdd"]

    # Unspecified solid-state style bus
    if bus_l in {"sata", "sas", "raid"} and not is_ssd:
        return "internal_hdd", HARDWARE_LABELS["internal_hdd"]

    # Letter D–Z Windows volumes with no SMART: still show something useful
    # Prefer portable for non-C letters on agent PCs full of external disks
    if letter_only and not path_l.startswith("c"):
        return "portable_hdd", HARDWARE_LABELS["portable_hdd"]
    if letter_only and path_l.startswith("c"):
        return "internal_hdd", HARDWARE_LABELS["internal_hdd"]

    return "unknown", HARDWARE_LABELS["unknown"]


# --- Linux local ---


def _block_device_for_path(path: str | Path) -> str | None:
    """Resolve /mnt/foo → /dev/sdb or /dev/nvme0n1 (whole disk)."""
    target = Path(path).expanduser()
    if not target.exists():
        return None
    findmnt = shutil.which("findmnt")
    if not findmnt:
        return None
    try:
        out = subprocess.check_output(
            [findmnt, "-n", "-o", "SOURCE", "--target", str(target)],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return None
    if not out or out.startswith("//") or ":" in out and not out.startswith("/dev"):
        # network mount — no local SMART
        return None
    # SOURCE may be /dev/sdb1, /dev/mapper/..., /dev/nvme0n1p1
    dev = out.split("[")[0].strip()
    if not dev.startswith("/dev/"):
        return None
    # Strip partition suffix for smartctl whole-disk
    name = Path(dev).name
    if name.startswith("nvme") and re.search(r"p\d+$", name):
        name = re.sub(r"p\d+$", "", name)
        return f"/dev/{name}"
    if re.match(r"^(sd|vd|hd)[a-z]+\d+$", name):
        name = re.sub(r"\d+$", "", name)
        return f"/dev/{name}"
    if name.startswith("mmcbLk") or name.startswith("mmcblk"):
        name = re.sub(r"p\d+$", "", name)
        return f"/dev/{name}"
    return dev


# ATA attribute ID / name → our field (bad-sector / integrity related)
_SECTOR_ATTR_MAP: dict[str, str] = {
    "5": "sector_reallocated",
    "reallocated_sector_ct": "sector_reallocated",
    "reallocated_sector_count": "sector_reallocated",
    "196": "sector_reallocated_events",  # event count — kept in attrs only
    "reallocated_event_count": "sector_reallocated_events",
    "197": "sector_pending",
    "current_pending_sector": "sector_pending",
    "198": "sector_uncorrectable",
    "offline_uncorrectable": "sector_uncorrectable",
    "offline_uncorrectable_sectors": "sector_uncorrectable",
    "199": "sector_crc",
    "udma_crc_error_count": "sector_crc",
    "187": "sector_reported_uncorrect",
    "reported_uncorrect": "sector_reported_uncorrect",
    "183": "sector_runtime_bad_block",
    "runtime_bad_block": "sector_runtime_bad_block",
}


def _raw_int(raw: str) -> int | None:
    """Parse SMART RAW_VALUE (may be '0', '10', or '45 (Min/Max 20/55)')."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text or text == "-":
        return None
    # First integer token
    m = re.match(r"([+-]?\d+)", text.replace(",", ""))
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def parse_sector_attributes(text: str) -> dict[str, Any]:
    """
    Extract bad-sector-related counters from smartctl -A / -x output.
    Works for classic ATA attribute tables and common NVMe log lines.
    """
    out: dict[str, Any] = {
        "sector_attrs_available": False,
        "sector_reallocated": None,
        "sector_pending": None,
        "sector_uncorrectable": None,
        "sector_crc": None,
        "sector_reported_uncorrect": None,
        "sector_reallocated_events": None,
        "sector_runtime_bad_block": None,
        "nvme_media_errors": None,
        "attrs": {},  # name → raw int
    }

    # ATA table rows: ID NAME FLAG VALUE WORST THRESH TYPE UPDATED WHEN_FAILED RAW
    # Flexible whitespace; RAW is last field(s)
    row_re = re.compile(
        r"^\s*(\d+)\s+([A-Za-z0-9_]+)\s+"
        r"0x[0-9a-fA-F]+\s+"
        r"\d+\s+\d+\s+\d+\s+"
        r"\S+\s+\S+\s+"
        r"(\S+)\s+"  # WHEN_FAILED
        r"(.+?)\s*$",
        re.MULTILINE,
    )
    for m in row_re.finditer(text):
        attr_id = m.group(1)
        name = m.group(2)
        raw = m.group(4).strip()
        val = _raw_int(raw)
        key_id = _SECTOR_ATTR_MAP.get(attr_id)
        key_name = _SECTOR_ATTR_MAP.get(name.lower())
        field = key_id or key_name
        if field and val is not None:
            out[field] = val
            out["attrs"][name] = val
            out["sector_attrs_available"] = True
        elif name.lower() in {
            "reallocated_sector_ct",
            "current_pending_sector",
            "offline_uncorrectable",
            "udma_crc_error_count",
            "reported_uncorrect",
        }:
            # Row matched name but raw parse failed — still mark available attempt
            out["attrs"][name] = raw

    # Fallback: looser match for attribute name anywhere with trailing number
    if not out["sector_attrs_available"]:
        for name, field in (
            ("Reallocated_Sector_Ct", "sector_reallocated"),
            ("Current_Pending_Sector", "sector_pending"),
            ("Offline_Uncorrectable", "sector_uncorrectable"),
            ("UDMA_CRC_Error_Count", "sector_crc"),
            ("Reported_Uncorrect", "sector_reported_uncorrect"),
        ):
            m = re.search(
                rf"{name}\s+.*?(\d+)\s*$",
                text,
                re.I | re.MULTILINE,
            )
            if m:
                out[field] = int(m.group(1))
                out["attrs"][name] = int(m.group(1))
                out["sector_attrs_available"] = True

    # NVMe SMART / Health Information
    nm = re.search(
        r"Media and Data Integrity Errors:\s*(\d+)",
        text,
        re.I,
    )
    if nm:
        out["nvme_media_errors"] = int(nm.group(1))
        out["sector_attrs_available"] = True
    # Some smartctl NVMe dumps
    nm2 = re.search(r"media_errors\s*[:=]\s*(\d+)", text, re.I)
    if nm2 and out["nvme_media_errors"] is None:
        out["nvme_media_errors"] = int(nm2.group(1))
        out["sector_attrs_available"] = True

    return out


def sector_risk_summary(sectors: dict[str, Any]) -> tuple[str, str, str]:
    """
    From sector attrs, return (status_hint, summary_text, severity_note).
    status_hint: '' | 'warning' | 'failing'
    """
    if not sectors.get("sector_attrs_available"):
        return (
            "",
            "Sector attributes not available (USB bridge, NAS, or no smartctl)",
            "",
        )

    realloc = sectors.get("sector_reallocated")
    pending = sectors.get("sector_pending")
    uncorr = sectors.get("sector_uncorrectable")
    crc = sectors.get("sector_crc")
    reported = sectors.get("sector_reported_uncorrect")
    nvme_err = sectors.get("nvme_media_errors")

    parts: list[str] = []
    status = ""

    def _n(v: Any) -> int:
        return int(v) if v is not None else 0

    if pending is not None:
        parts.append(f"Pending sectors: {pending}")
        if _n(pending) > 0:
            status = "failing"
    if uncorr is not None:
        parts.append(f"Offline uncorrectable: {uncorr}")
        if _n(uncorr) > 0:
            status = "failing"
    if realloc is not None:
        parts.append(f"Reallocated sectors: {realloc}")
        if _n(realloc) > 0 and status != "failing":
            status = "warning"
        if _n(realloc) >= 100:
            status = "failing"
    if reported is not None:
        parts.append(f"Reported uncorrectable: {reported}")
        if _n(reported) > 0 and status != "failing":
            status = "warning"
        if _n(reported) >= 10:
            status = "failing"
    if crc is not None:
        parts.append(f"UDMA CRC errors: {crc}")
        # CRC is often cable/dock — warn only if high
        if _n(crc) >= 50 and status != "failing":
            status = "warning"
    if nvme_err is not None:
        parts.append(f"NVMe media errors: {nvme_err}")
        if _n(nvme_err) > 0:
            status = "failing"

    if not parts:
        return "", "No sector-related SMART attributes found in output", ""

    if status == "failing":
        note = "Bad/pending sector activity detected — back up and replace if values rise"
    elif status == "warning":
        note = "Some reallocated or integrity counters are non-zero — monitor closely"
    else:
        note = "Sector counters look clean (all zero or within cable-noise range)"

    return status, "; ".join(parts), note


def merge_status(base: str, hint: str) -> str:
    """Escalate health: failing > warning > healthy/unknown."""
    order = {"unknown": 0, "healthy": 1, "warning": 2, "failing": 3}
    b = normalize_status(base)
    h = normalize_status(hint) if hint else ""
    if not h:
        return b
    return h if order.get(h, 0) >= order.get(b, 0) else b


def _parse_smartctl(text: str) -> dict[str, Any]:
    status_raw = ""
    m = re.search(
        r"SMART overall-health self-assessment test result:\s*(\S+)",
        text,
        re.I,
    )
    if m:
        status_raw = m.group(1)
    else:
        m = re.search(r"SMART Health Status:\s*(.+)", text, re.I)
        if m:
            status_raw = m.group(1).strip()

    temp = None
    for pat in (
        r"Temperature_Celsius\s+\S+\s+\d+\s+\d+\s+\d+\s+\S+\s+\S+\s+\S+\s+(\d+)",
        r"Current Drive Temperature:\s*(\d+)",
        r"Temperature:\s*(\d+)\s*Celsius",
        r"Airflow_Temperature_Cel\s+\S+\s+\d+\s+\d+\s+\d+\s+\S+\s+\S+\s+\S+\s+(\d+)",
    ):
        tm = re.search(pat, text, re.I)
        if tm:
            temp = int(tm.group(1))
            break

    model = ""
    serial = ""
    mm = re.search(r"Device Model:\s*(.+)", text)
    if mm:
        model = mm.group(1).strip()
    else:
        mm = re.search(r"Model Number:\s*(.+)", text)
        if mm:
            model = mm.group(1).strip()
    sm = re.search(r"Serial Number:\s*(.+)", text)
    if sm:
        serial = sm.group(1).strip()

    status = normalize_status(status_raw)
    if not status_raw and "SMART support is: Unavailable" in text:
        status = "unknown"
        status_raw = "unavailable"

    # Rotation / form factor hints from smartctl identity block
    media = ""
    bus = ""
    if re.search(r"Rotation Rate:\s*Solid State", text, re.I):
        media = "SSD"
    elif re.search(r"Rotation Rate:\s*\d+", text, re.I):
        media = "HDD"
    if re.search(r"NVMe", text, re.I) or "nvme" in (model or "").lower():
        bus = "NVMe"
        media = media or "SSD"
    elif re.search(r"SATA|Serial ATA", text, re.I):
        bus = "SATA"
    elif re.search(r"USB", text, re.I):
        bus = "USB"

    sectors = parse_sector_attributes(text)
    hint, summary, note = sector_risk_summary(sectors)
    status = merge_status(status, hint)

    detail_bits = [summary]
    if note:
        detail_bits.append(note)
    # Keep a short slice of raw smartctl for debug
    detail = " · ".join(detail_bits)

    return empty_report(
        status=status,
        status_raw=status_raw or status,
        temperature_c=temp,
        model=model,
        serial=serial,
        media=media,
        bus=bus,
        source="smartctl",
        detail=detail[:2000],
        ok=True,
        sector_attrs_available=bool(sectors.get("sector_attrs_available")),
        sector_reallocated=sectors.get("sector_reallocated"),
        sector_pending=sectors.get("sector_pending"),
        sector_uncorrectable=sectors.get("sector_uncorrectable"),
        sector_crc=sectors.get("sector_crc"),
        sector_reported_uncorrect=sectors.get("sector_reported_uncorrect"),
        nvme_media_errors=sectors.get("nvme_media_errors"),
        sector_summary=summary,
        sector_note=note,
        sector_attrs=sectors.get("attrs") or {},
    )


def _linux_lsblk_hints(dev: str) -> dict[str, str]:
    """ROTA / TRAN from lsblk for better SSD vs HDD / bus detection."""
    lsblk = shutil.which("lsblk")
    if not lsblk:
        return {}
    try:
        out = subprocess.check_output(
            [lsblk, "-ndo", "NAME,ROTA,TRAN,TYPE,RM", dev],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return {}
    # Example: sdb 1 usb disk 0
    parts = out.split()
    hints: dict[str, str] = {}
    if len(parts) >= 2:
        rota = parts[1]
        hints["media"] = "HDD" if rota == "1" else "SSD"
    if len(parts) >= 3 and parts[2] and parts[2] != "-":
        hints["bus"] = parts[2].upper()  # usb, sata, nvme…
    if len(parts) >= 5 and parts[4] == "1":
        hints["drive_type"] = "Removable"
    if "nvme" in dev:
        hints["bus"] = "NVMe"
        hints["media"] = "SSD"
    return hints


def probe_local_smart(path: str | Path) -> dict[str, Any]:
    """Run smartctl against the block device backing a local mount path."""
    smartctl = shutil.which("smartctl")
    dev = _block_device_for_path(path)
    if not dev:
        return empty_report(
            detail="No local block device for this path (network mount or unknown)",
            source="local",
            drive_type="Network" if "://" in str(path) or str(path).startswith("//") else "",
        )

    hints = _linux_lsblk_hints(dev)
    if not smartctl:
        hw_type, hw_label = classify_drive_hardware(
            media=hints.get("media", ""),
            bus=hints.get("bus", ""),
            drive_type=hints.get("drive_type", ""),
            device=dev,
        )
        return empty_report(
            detail="smartctl not installed (sudo apt install smartmontools)",
            source="local",
            media=hints.get("media", ""),
            bus=hints.get("bus", ""),
            drive_type=hints.get("drive_type", ""),
            device=dev,
            hardware_type=hw_type,
            hardware_label=hw_label,
            ok=True,
        )
    try:
        proc = subprocess.run(
            [smartctl, "-H", "-A", "-i", dev],
            capture_output=True,
            text=True,
            timeout=30,
        )
        text = (proc.stdout or "") + "\n" + (proc.stderr or "")
        # smartctl exits non-zero when bits indicate failure — still parse
        report = _parse_smartctl(text)
        report["device"] = dev
        report["source"] = f"smartctl:{dev}"
        # Prefer lsblk when smartctl left media/bus empty
        if not report.get("media") and hints.get("media"):
            report["media"] = hints["media"]
        if not report.get("bus") and hints.get("bus"):
            report["bus"] = hints["bus"]
        if hints.get("drive_type"):
            report["drive_type"] = hints["drive_type"]
        if proc.returncode and report["status"] == "unknown":
            # bitmask: 8 = SMART overall failure
            if proc.returncode & 8:
                report["status"] = "failing"
                report["status_raw"] = "FAILED"
            elif proc.returncode & 16:
                report["status"] = "warning"
        report["ok"] = True
        hw_type, hw_label = classify_drive_hardware(
            media=str(report.get("media") or ""),
            bus=str(report.get("bus") or ""),
            drive_type=str(report.get("drive_type") or ""),
            model=str(report.get("model") or ""),
            detail=str(report.get("detail") or ""),
            device=dev,
        )
        report["hardware_type"] = hw_type
        report["hardware_label"] = hw_label
        return report
    except subprocess.TimeoutExpired:
        return empty_report(detail="smartctl timed out", source="local")
    except OSError as exc:
        return empty_report(detail=str(exc), source="local")


# --- Normalize agent / PowerShell payloads ---


def normalize_agent_smart(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not payload:
        return empty_report(detail="No SMART data from agent")
    status = normalize_status(
        payload.get("status")
        or payload.get("health")
        or payload.get("HealthStatus")
        or payload.get("status_raw")
    )
    temp = payload.get("temperature_c")
    if temp is None:
        temp = payload.get("temperature")
    try:
        temp = int(temp) if temp is not None and str(temp).strip() != "" else None
    except (TypeError, ValueError):
        temp = None
    media = str(payload.get("media") or payload.get("MediaType") or "")
    bus = str(payload.get("bus") or payload.get("BusType") or "")
    drive_type = str(payload.get("drive_type") or payload.get("DriveType") or "")
    model = str(payload.get("model") or payload.get("FriendlyName") or "")
    detail = str(payload.get("detail") or payload.get("error") or "")[:2000]
    device = str(payload.get("device") or "")
    hw_type, hw_label = classify_drive_hardware(
        media=media,
        bus=bus,
        drive_type=drive_type,
        model=model,
        detail=detail,
        device=device,
    )
    # Prefer agent-supplied classification if valid
    if payload.get("hardware_type") in HARDWARE_LABELS:
        hw_type = str(payload["hardware_type"])
        hw_label = hardware_label(hw_type)
    volume_label = str(payload.get("volume_label") or "")
    report = empty_report(
        status=status,
        status_raw=str(
            payload.get("status_raw")
            or payload.get("health")
            or payload.get("HealthStatus")
            or status
        ),
        temperature_c=temp,
        model=model,
        serial=str(payload.get("serial") or ""),
        media=media,
        bus=bus,
        drive_type=drive_type,
        source=str(payload.get("source") or "agent"),
        detail=detail,
        ok=bool(payload.get("ok", True)),
        device=device,
        hardware_type=hw_type,
        hardware_label=hw_label,
        volume_label=volume_label,
    )
    # Pass through sector fields from agent/smartctl merge
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
        if key in payload and payload[key] is not None:
            report[key] = payload[key]
    if report.get("sector_attrs_available"):
        hint, summary, note = sector_risk_summary(
            {
                "sector_attrs_available": True,
                "sector_reallocated": report.get("sector_reallocated"),
                "sector_pending": report.get("sector_pending"),
                "sector_uncorrectable": report.get("sector_uncorrectable"),
                "sector_crc": report.get("sector_crc"),
                "sector_reported_uncorrect": report.get("sector_reported_uncorrect"),
                "nvme_media_errors": report.get("nvme_media_errors"),
            }
        )
        report["status"] = merge_status(report["status"], hint)
        if summary:
            report["sector_summary"] = summary
            report["detail"] = (summary + (" · " + note if note else ""))[:2000]
    return report


def report_to_storage(report: dict[str, Any]) -> dict[str, Any]:
    """Flatten for DB columns."""
    status = normalize_status(report.get("status"))
    media = str(report.get("media") or "")
    bus = str(report.get("bus") or "")
    drive_type = str(report.get("drive_type") or "")
    model = str(report.get("model") or "")
    detail = str(report.get("detail") or "")
    device = str(report.get("device") or "")
    hw_type = report.get("hardware_type")
    hw_label = report.get("hardware_label")
    if not hw_type or hw_type == "unknown":
        hw_type, hw_label = classify_drive_hardware(
            media=media,
            bus=bus,
            drive_type=drive_type,
            model=model,
            detail=detail,
            device=device,
        )
    else:
        hw_label = hw_label or hardware_label(str(hw_type))

    # Re-evaluate sector risk if attrs present in report
    sectors = {
        "sector_attrs_available": bool(report.get("sector_attrs_available")),
        "sector_reallocated": report.get("sector_reallocated"),
        "sector_pending": report.get("sector_pending"),
        "sector_uncorrectable": report.get("sector_uncorrectable"),
        "sector_crc": report.get("sector_crc"),
        "sector_reported_uncorrect": report.get("sector_reported_uncorrect"),
        "nvme_media_errors": report.get("nvme_media_errors"),
    }
    hint, summary, note = sector_risk_summary(sectors)
    if sectors["sector_attrs_available"]:
        status = merge_status(status, hint)
        if summary:
            detail = (summary + (" · " + note if note else ""))[:4000]
    elif not report.get("sector_summary"):
        # Keep existing detail; note unavailability if empty
        pass

    return {
        "smart_status": status,
        "smart_status_raw": str(report.get("status_raw") or "")[:120],
        "smart_temperature_c": report.get("temperature_c"),
        "smart_model": model[:200],
        "smart_serial": str(report.get("serial") or "")[:120],
        "smart_media": media[:80],
        "smart_bus": bus[:80],
        "hardware_type": str(hw_type)[:40],
        "hardware_label": str(hw_label)[:80],
        "smart_source": str(report.get("source") or "")[:120],
        "smart_detail": (detail or str(report.get("sector_summary") or ""))[:4000],
        "smart_json": json.dumps(report, default=str)[:12000],
        "sector_attrs_available": 1 if sectors["sector_attrs_available"] else 0,
        "sector_reallocated": report.get("sector_reallocated"),
        "sector_pending": report.get("sector_pending"),
        "sector_uncorrectable": report.get("sector_uncorrectable"),
        "sector_crc": report.get("sector_crc"),
        "sector_reported_uncorrect": report.get("sector_reported_uncorrect"),
        "nvme_media_errors": report.get("nvme_media_errors"),
        "sector_summary": (
            str(report.get("sector_summary") or summary or "")[:500]
        ),
        "volume_label": str(report.get("volume_label") or "")[:120],
        "capacity_total_bytes": report.get("total_bytes")
        if report.get("total_bytes") is not None
        else report.get("capacity_total_bytes"),
        "capacity_free_bytes": report.get("free_bytes")
        if report.get("free_bytes") is not None
        else report.get("capacity_free_bytes"),
        "capacity_used_bytes": report.get("used_bytes")
        if report.get("used_bytes") is not None
        else report.get("capacity_used_bytes"),
    }
