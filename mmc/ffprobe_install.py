"""Install a local ffprobe binary if the file-host does not already have one."""

from __future__ import annotations

import os
import platform
import shutil
import stat
import subprocess
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from mmc.config import BASE_DIR

TOOLS_DIR = BASE_DIR / "tools" / "ffmpeg"

# Official community static builds (same sources ffmpeg.org documents).
_LINUX_URLS = (
    "https://github.com/ffbinaries/ffbinaries-prebuilt/releases/download/v6.1/ffprobe-6.1-linux-64.zip",
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz",
    "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz",
)
_LINUX_ARM_URLS = (
    "https://github.com/ffbinaries/ffbinaries-prebuilt/releases/download/v6.1/ffprobe-6.1-linux-arm-64.zip",
    "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-arm64-static.tar.xz",
)
_WIN_URLS = (
    "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
)

_UA = "MultiMedia.Comparator/1.0 (ffprobe-install)"


class FfprobeInstallError(Exception):
    pass


def _is_win() -> bool:
    return platform.system() == "Windows"


def _ffprobe_name() -> str:
    return "ffprobe.exe" if _is_win() else "ffprobe"


def bundled_ffprobe() -> Path:
    return TOOLS_DIR / _ffprobe_name()


def find_ffprobe() -> str | None:
    """PATH first, then the portable copy next to this app."""
    found = shutil.which("ffprobe") or shutil.which("ffprobe.exe")
    if found:
        return found
    portable = bundled_ffprobe()
    if portable.is_file() and os.access(portable, os.X_OK):
        return str(portable)
    return None


def _looks_like_ffprobe(path: Path) -> bool:
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


def _download(url: str, dest: Path, timeout: float = 180.0) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = Request(url, headers={"User-Agent": _UA})
    with urlopen(req, timeout=timeout) as resp, dest.open("wb") as fh:
        shutil.copyfileobj(resp, fh)
    if dest.stat().st_size < 200_000:
        raise FfprobeInstallError(f"download too small from {url}")


def _copy_ffprobe_from_tree(root: Path, dest: Path) -> Path:
    matches = list(root.rglob(_ffprobe_name()))
    if not matches:
        raise FfprobeInstallError(f"archive had no {_ffprobe_name()}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(matches[0], dest)
    dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    # Gyan/BtbN static builds are self-contained; copy sibling DLLs if present
    for sib in matches[0].parent.glob("*.dll"):
        shutil.copy2(sib, dest.parent / sib.name)
    return dest


def _extract_archive(archive: Path, dest_dir: Path) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    name = archive.name.lower()
    if name.endswith(".zip"):
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(dest_dir)
        return
    if name.endswith(".tar.xz") or name.endswith(".txz") or name.endswith(".tar.gz"):
        with tarfile.open(archive) as tf:
            tf.extractall(dest_dir)
        return
    raise FfprobeInstallError(f"unsupported archive: {archive.name}")


def _try_apt() -> str | None:
    if shutil.which("ffprobe"):
        return shutil.which("ffprobe")
    apt = shutil.which("apt-get")
    if not apt:
        return None
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        cmd = [apt, "-y", "install", "ffmpeg"]
    elif shutil.which("sudo"):
        probe = subprocess.run(
            ["sudo", "-n", "true"], capture_output=True, timeout=8
        )
        if probe.returncode != 0:
            return None
        cmd = ["sudo", "-n", apt, "-y", "install", "ffmpeg"]
    else:
        return None
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return shutil.which("ffprobe")


def _urls_for_host() -> tuple[str, ...]:
    if _is_win():
        return _WIN_URLS
    machine = (platform.machine() or "").lower()
    if machine in {"aarch64", "arm64"}:
        return _LINUX_ARM_URLS
    return _LINUX_URLS


def install_ffprobe(force: bool = False) -> dict[str, Any]:
    """
    Put ffprobe on this machine. Prefers PATH / apt, then a portable build
    under tools/ffmpeg/. Does not ask — that is the 'if needed' force.
    """
    existing = find_ffprobe()
    if existing and not force:
        return {
            "ok": True,
            "installed": False,
            "path": existing,
            "source": "existing",
            "detail": "ffprobe already present",
        }

    if not _is_win() and not force:
        apt_path = _try_apt()
        if apt_path:
            return {
                "ok": True,
                "installed": True,
                "path": apt_path,
                "source": "apt",
                "detail": "installed ffmpeg via apt-get",
            }

    dest = bundled_ffprobe()
    last_err = ""
    with tempfile.TemporaryDirectory(prefix="mmc-ffprobe-") as tmp:
        tmp_path = Path(tmp)
        for url in _urls_for_host():
            archive = tmp_path / ("pack.zip" if url.endswith(".zip") else "pack.tar.xz")
            try:
                _download(url, archive)
                extract_to = tmp_path / "out"
                _extract_archive(archive, extract_to)
                _copy_ffprobe_from_tree(extract_to, dest)
                if not _looks_like_ffprobe(dest):
                    raise FfprobeInstallError("extracted binary did not run as ffprobe")
                return {
                    "ok": True,
                    "installed": True,
                    "path": str(dest),
                    "source": "portable",
                    "detail": f"downloaded from {url}",
                }
            except Exception as exc:  # noqa: BLE001
                last_err = f"{url}: {exc}"
                continue

    raise FfprobeInstallError(
        "Could not install ffprobe on this file host. "
        + (last_err or "no download source succeeded")
    )


def ensure_ffprobe(force: bool = False) -> str:
    """Return an ffprobe path, installing if missing (or if force=True)."""
    report = install_ffprobe(force=force)
    path = report.get("path") or ""
    if not path:
        raise FfprobeInstallError(report.get("detail") or "ffprobe missing")
    return str(path)
