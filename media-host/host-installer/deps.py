"""Detect and install file-host tools: ffprobe, CrystalDiskInfo, smartctl."""

from __future__ import annotations

import os
import platform
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

UA = "MediaHostSetup/1.6"
AGENT_PORT = 8766
FIREWALL_RULE = "Media Catalog Agent"

CDI_URLS = (
    "https://downloads.sourceforge.net/project/crystaldiskinfo/9.7.2/CrystalDiskInfo9_7_2.zip",
    "https://github.com/hiyohiyo/CrystalDiskInfo/releases/download/9.7.2/CrystalDiskInfo9_7_2.zip",
)


def _is_win() -> bool:
    return platform.system() == "Windows"


def lan_ip() -> str:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        return ip
    except OSError:
        return "127.0.0.1"


def python_info() -> dict[str, Any]:
    exe = sys.executable or ""
    return {
        "ok": sys.version_info >= (3, 9),
        "path": exe,
        "version": platform.python_version(),
        "impl": platform.python_implementation(),
    }


def _download(url: str, dest: Path, timeout: float = 180.0) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = Request(url, headers={"User-Agent": UA})
    with urlopen(req, timeout=timeout) as resp, dest.open("wb") as fh:
        shutil.copyfileobj(resp, fh)
    if dest.stat().st_size < 80_000:
        raise RuntimeError(f"download too small: {url}")


def ffprobe_status() -> dict[str, Any]:
    try:
        from agent import find_ffprobe
    except Exception:  # noqa: BLE001
        find_ffprobe = None  # type: ignore[assignment]
    path = find_ffprobe() if find_ffprobe else (
        shutil.which("ffprobe") or shutil.which("ffprobe.exe")
    )
    return {
        "id": "ffprobe",
        "label": "ffprobe (deep scan)",
        "ok": bool(path),
        "path": path or "",
        "detail": path or "Not installed — needed to read real video/audio streams",
    }


def install_ffprobe(force: bool = False) -> dict[str, Any]:
    from agent import install_ffprobe as _install

    return _install(force=force)


def crystaldisk_status() -> dict[str, Any]:
    try:
        from crystaldisk import find_crystaldisk_exe

        exe = find_crystaldisk_exe()
    except Exception:  # noqa: BLE001
        exe = None
    if not _is_win():
        return {
            "id": "smart",
            "label": "CrystalDiskInfo",
            "ok": False,
            "path": "",
            "skip": True,
            "detail": "Windows only — Linux uses smartctl",
        }
    return {
        "id": "smart",
        "label": "CrystalDiskInfo (SMART)",
        "ok": bool(exe),
        "path": str(exe) if exe else "",
        "detail": str(exe) if exe else "Not found — needed for USB / external drive health",
    }


def smartctl_status() -> dict[str, Any]:
    path = shutil.which("smartctl")
    return {
        "id": "smartctl",
        "label": "smartctl (SMART)",
        "ok": bool(path),
        "path": path or "",
        "detail": path or "Not installed — sudo apt install smartmontools",
    }


def install_crystaldisk(force: bool = False) -> dict[str, Any]:
    if not _is_win():
        return {"ok": False, "detail": "CrystalDiskInfo is Windows-only"}
    current = crystaldisk_status()
    if current["ok"] and not force:
        return {
            "ok": True,
            "installed": False,
            "path": current["path"],
            "source": "existing",
            "detail": "CrystalDiskInfo already present",
        }

    winget = shutil.which("winget")
    if winget and not force:
        try:
            proc = subprocess.run(
                [
                    winget,
                    "install",
                    "-e",
                    "--id",
                    "CrystalDewWorld.CrystalDiskInfo",
                    "--accept-package-agreements",
                    "--accept-source-agreements",
                    "--disable-interactivity",
                ],
                capture_output=True,
                text=True,
                timeout=300,
            )
            after = crystaldisk_status()
            if after["ok"]:
                return {
                    "ok": True,
                    "installed": True,
                    "path": after["path"],
                    "source": "winget",
                    "detail": "Installed CrystalDiskInfo with winget",
                }
            if proc.returncode != 0:
                pass
        except (OSError, subprocess.TimeoutExpired):
            pass

    dest_dir = REPO / "tools" / "CrystalDiskInfo"
    last_err = ""
    with tempfile.TemporaryDirectory(prefix="cdi-") as tmp:
        tmp_path = Path(tmp)
        for url in CDI_URLS:
            archive = tmp_path / "cdi.zip"
            try:
                _download(url, archive)
                extract = tmp_path / "out"
                extract.mkdir()
                with zipfile.ZipFile(archive) as zf:
                    zf.extractall(extract)
                exe = None
                for name in ("DiskInfo64.exe", "DiskInfoA64.exe", "DiskInfo32.exe", "DiskInfo.exe"):
                    hits = list(extract.rglob(name))
                    if hits:
                        exe = hits[0]
                        break
                if not exe:
                    raise RuntimeError("zip had no DiskInfo exe")
                dest_dir.mkdir(parents=True, exist_ok=True)
                # Copy the folder that contains the exe so Cdi stays together
                src_root = exe.parent
                if dest_dir.exists():
                    for child in dest_dir.iterdir():
                        if child.is_file():
                            child.unlink()
                for item in src_root.iterdir():
                    target = dest_dir / item.name
                    if item.is_dir():
                        if target.exists():
                            shutil.rmtree(target)
                        shutil.copytree(item, target)
                    else:
                        shutil.copy2(item, target)
                found = dest_dir / exe.name
                if not found.is_file():
                    raise RuntimeError("copy failed")
                os.environ["CRYSTALDISKINFO_PATH"] = str(found)
                return {
                    "ok": True,
                    "installed": True,
                    "path": str(found),
                    "source": "portable",
                    "detail": f"Installed portable CrystalDiskInfo from {url}",
                }
            except Exception as exc:  # noqa: BLE001
                last_err = f"{url}: {exc}"
                continue
    return {
        "ok": False,
        "installed": False,
        "path": "",
        "source": "none",
        "detail": last_err or "Could not download CrystalDiskInfo",
    }


def install_smartctl() -> dict[str, Any]:
    if _is_win():
        return {"ok": False, "detail": "On Windows use CrystalDiskInfo"}
    existing = shutil.which("smartctl")
    if existing:
        return {
            "ok": True,
            "installed": False,
            "path": existing,
            "source": "existing",
            "detail": "smartctl already present",
        }
    apt = shutil.which("apt-get")
    if not apt:
        return {"ok": False, "detail": "apt-get not found — install smartmontools"}
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        cmd = [apt, "-y", "install", "smartmontools", "ffmpeg"]
    elif shutil.which("sudo"):
        chk = subprocess.run(["sudo", "-n", "true"], capture_output=True, timeout=8)
        if chk.returncode != 0:
            return {
                "ok": False,
                "detail": "Need sudo to install smartmontools (sudo apt install smartmontools)",
            }
        cmd = ["sudo", "-n", apt, "-y", "install", "smartmontools", "ffmpeg"]
    else:
        return {"ok": False, "detail": "No sudo — install smartmontools by hand"}
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "detail": str(exc)}
    path = shutil.which("smartctl")
    if path:
        return {
            "ok": True,
            "installed": True,
            "path": path,
            "source": "apt",
            "detail": "Installed smartmontools via apt",
        }
    return {
        "ok": False,
        "detail": (proc.stderr or proc.stdout or "apt failed")[:300],
    }


def _windows_is_admin() -> bool:
    if not _is_win():
        return False
    try:
        import ctypes

        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:  # noqa: BLE001
        return False


def _firewall_rule_present(output: str, returncode: int) -> bool:
    text = output or ""
    if returncode != 0 or "No rules match" in text:
        return False
    return FIREWALL_RULE in text


def firewall_rule_exists() -> bool:
    if not _is_win():
        return False
    try:
        proc = subprocess.run(
            [
                "netsh",
                "advfirewall",
                "firewall",
                "show",
                "rule",
                f"name={FIREWALL_RULE}",
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return _firewall_rule_present((proc.stdout or "") + (proc.stderr or ""), proc.returncode)


def firewall_status() -> dict[str, Any]:
    if _is_win():
        if firewall_rule_exists():
            return {
                "id": "firewall",
                "label": f"Firewall TCP {AGENT_PORT}",
                "ok": True,
                "needs_admin": False,
                "detail": f"Inbound TCP {AGENT_PORT} is already allowed",
            }
        return {
            "id": "firewall",
            "label": f"Firewall TCP {AGENT_PORT}",
            "ok": None,
            "needs_admin": True,
            "detail": (
                "Click Open firewall. Windows will ask “Do you want to allow this app "
                "to make changes?” — click Yes. (The setup page cannot take an admin password.)"
            ),
        }
    if platform.system() == "Darwin":
        return {
            "id": "firewall",
            "label": f"Firewall TCP {AGENT_PORT}",
            "ok": None,
            "detail": (
                "macOS: System Settings → Network → Firewall → Options → allow "
                "incoming connections for Python on TCP 8766"
            ),
        }
    ufw = shutil.which("ufw")
    if not ufw:
        return {
            "id": "firewall",
            "label": f"Firewall TCP {AGENT_PORT}",
            "ok": True,
            "detail": "No ufw — if you have another firewall, allow TCP 8766",
        }
    return {
        "id": "firewall",
        "label": f"ufw TCP {AGENT_PORT}",
        "ok": None,
        "detail": "Will run: ufw allow 8766/tcp",
    }


def _netsh_add_firewall() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "netsh",
            "advfirewall",
            "firewall",
            "add",
            "rule",
            f"name={FIREWALL_RULE}",
            "dir=in",
            "action=allow",
            "protocol=TCP",
            f"localport={AGENT_PORT}",
            "profile=any",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )


def _elevate_firewall_rule() -> dict[str, Any]:
    """Pop the Windows UAC Yes/No prompt, then add the rule as Administrator."""
    script = Path(__file__).resolve().parent / "open-firewall.ps1"
    if script.is_file():
        cmd = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-Port",
            str(AGENT_PORT),
            "-RuleName",
            FIREWALL_RULE,
        ]
    else:
        ps = (
            "$ErrorActionPreference='Stop'; "
            f"$arg='advfirewall firewall add rule name=\"{FIREWALL_RULE}\" "
            f"dir=in action=allow protocol=TCP localport={AGENT_PORT} profile=any'; "
            "try { $p = Start-Process -FilePath netsh -Verb RunAs -ArgumentList $arg "
            "-Wait -PassThru; exit $p.ExitCode } "
            "catch { Write-Output $_.Exception.Message; exit 2 }"
        )
        cmd = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            ps,
        ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "detail": (
                "Timed out waiting for the Windows permission prompt. "
                "It may be behind the browser — look at the taskbar, click Yes, then try again."
            ),
        }
    except OSError as exc:
        return {"ok": False, "detail": str(exc)}
    text = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    if firewall_rule_exists():
        return {"ok": True, "detail": f"Allowed inbound TCP {AGENT_PORT} (Admin prompt accepted)"}
    if proc.returncode == 2 or "UAC_CANCELLED" in text or "canceled" in text.lower() or "cancelled" in text.lower():
        return {
            "ok": False,
            "detail": (
                "The Windows prompt was dismissed. Click Open firewall again and choose Yes. "
                "Or double-click OPEN_FIREWALL.bat and click Yes there."
            ),
        }
    return {
        "ok": False,
        "detail": (
            (text or "Could not add the firewall rule")[:280]
            + " — double-click OPEN_FIREWALL.bat and click Yes on the prompt."
        ),
    }


def open_firewall() -> dict[str, Any]:
    if _is_win():
        if firewall_rule_exists():
            return {"ok": True, "detail": f"Inbound TCP {AGENT_PORT} is already allowed"}
        if _windows_is_admin():
            try:
                proc = _netsh_add_firewall()
            except (OSError, subprocess.TimeoutExpired) as exc:
                return {"ok": False, "detail": str(exc)}
            if proc.returncode == 0 or firewall_rule_exists():
                return {"ok": True, "detail": f"Allowed inbound TCP {AGENT_PORT}"}
            return {
                "ok": False,
                "detail": (proc.stderr or proc.stdout or "netsh failed")[:300],
            }
        # Browser/wizard cannot collect an admin password. This pops the Yes/No UAC box.
        return _elevate_firewall_rule()
    if platform.system() == "Darwin":
        return {
            "ok": True,
            "detail": (
                "Allow incoming Python in System Settings → Network → Firewall "
                f"for TCP {AGENT_PORT}"
            ),
        }
    ufw = shutil.which("ufw")
    if not ufw:
        return {"ok": True, "detail": "No ufw to configure"}
    cmd = [ufw, "allow", f"{AGENT_PORT}/tcp"]
    if shutil.which("sudo") and not (hasattr(os, "geteuid") and os.geteuid() == 0):
        cmd = ["sudo", "-n"] + cmd
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "detail": str(exc)}
    if proc.returncode == 0:
        return {"ok": True, "detail": f"ufw allowed {AGENT_PORT}/tcp"}
    return {"ok": False, "detail": (proc.stderr or "ufw failed")[:300]}


def agent_running() -> bool:
    try:
        req = Request(
            f"http://127.0.0.1:{AGENT_PORT}/api/health",
            headers={"User-Agent": UA, "Accept": "application/json"},
        )
        with urlopen(req, timeout=2) as resp:
            return resp.status == 200
    except Exception:  # noqa: BLE001
        return False


def start_agent() -> dict[str, Any]:
    if agent_running():
        return {
            "ok": True,
            "already": True,
            "detail": f"Agent already answering on port {AGENT_PORT}",
        }
    agent = REPO / "agent.py"
    if not agent.is_file():
        return {"ok": False, "detail": f"agent.py missing at {agent}"}
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO) + os.pathsep + env.get("PYTHONPATH", "")
    kwargs: dict[str, Any] = {
        "cwd": str(REPO),
        "env": env,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if _is_win():
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
        kwargs["close_fds"] = True
    else:
        kwargs["start_new_session"] = True
    try:
        subprocess.Popen([sys.executable, str(agent), "--host", "0.0.0.0", "--port", str(AGENT_PORT)], **kwargs)
    except OSError as exc:
        return {"ok": False, "detail": str(exc)}
    return {
        "ok": True,
        "already": False,
        "detail": f"Started agent on port {AGENT_PORT}",
    }


def host_status() -> dict[str, Any]:
    system = platform.system()
    py = python_info()
    py["id"] = "python"
    py["label"] = "Python 3"
    py["detail"] = f"{py['version']} · {py['path']}" if py.get("path") else "Python 3.9+ required"
    ff = ffprobe_status()
    if system == "Windows":
        smart = crystaldisk_status()
    else:
        smart = smartctl_status()
        smart["id"] = "smart"
    fw = firewall_status()
    running = agent_running()
    ip = lan_ip()
    return {
        "os": system,
        "os_label": "Windows" if system == "Windows" else system,
        "linux": system != "Windows",
        "hostname": platform.node(),
        "arch": platform.machine(),
        "python": py,
        "ffprobe": ff,
        "smart": smart,
        "firewall": fw,
        "agent": {
            "id": "agent",
            "label": "Media host agent",
            "ok": running,
            "running": running,
            "port": AGENT_PORT,
            "url": f"http://{ip}:{AGENT_PORT}",
            "local_url": f"http://127.0.0.1:{AGENT_PORT}",
            "detail": f"Listening on {ip}:{AGENT_PORT}" if running else "Not running yet",
        },
        "lan_ip": ip,
        "port": AGENT_PORT,
        "ready": bool(py["ok"] and ff["ok"] and running),
        "version": "1.6",
    }


def run_step(step: str, force: bool = False) -> dict[str, Any]:
    step = (step or "").strip().lower()
    if step == "ffprobe":
        return install_ffprobe(force=force)
    if step == "smart":
        if _is_win():
            return install_crystaldisk(force=force)
        return install_smartctl()
    if step == "firewall":
        return open_firewall()
    if step == "agent":
        return start_agent()
    return {"ok": False, "detail": f"unknown step {step}"}


def chmod_self(path: Path) -> None:
    try:
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except OSError:
        pass
