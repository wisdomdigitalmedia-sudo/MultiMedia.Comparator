"""Detect this machine, scan the LAN, and recommend a catalog/agent install."""

from __future__ import annotations

import ipaddress
import json
import platform
import socket
import subprocess
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

AGENT_PORT = 8766
CATALOG_PORT = 8767


def this_os() -> str:
    system = platform.system()
    if system == "Windows":
        return "windows"
    if system == "Darwin":
        return "mac"
    return "linux"


def lan_ip() -> str:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        return ip
    except OSError:
        return "127.0.0.1"


def subnet_hosts(ip: str) -> list[str]:
    try:
        net = ipaddress.ip_network(ip + "/24", strict=False)
    except ValueError:
        return []
    me = ipaddress.ip_address(ip)
    return [str(h) for h in net.hosts() if h != me]


def _tcp_open(ip: str, port: int, timeout: float) -> bool:
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except OSError:
        return False


def _http_json(url: str, timeout: float = 1.2) -> dict[str, Any] | None:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            data = json.loads(raw) if raw else {}
            return data if isinstance(data, dict) else None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None


def probe_host(ip: str, timeout: float = 0.35) -> dict[str, Any] | None:
    agent = _tcp_open(ip, AGENT_PORT, timeout)
    catalog = _tcp_open(ip, CATALOG_PORT, timeout)
    if not agent and not catalog:
        return None
    out: dict[str, Any] = {
        "ip": ip,
        "agent": False,
        "catalog": False,
        "agent_url": f"http://{ip}:{AGENT_PORT}",
        "catalog_url": f"http://{ip}:{CATALOG_PORT}",
        "hostname": "",
        "agent_os": "",
        "detail": "",
        "this_machine": False,
    }
    if agent:
        health = _http_json(f"http://{ip}:{AGENT_PORT}/api/health", timeout=1.5)
        out["agent"] = True
        if health:
            out["hostname"] = str(health.get("hostname") or "")
            plat = str(health.get("platform") or "")
            out["agent_os"] = plat.lower() if plat else ""
            out["detail"] = (
                f"Media host agent {health.get('version') or ''} "
                f"({plat or 'unknown OS'})"
            ).strip()
        else:
            out["detail"] = "Port 8766 open (agent?)"
    if catalog:
        out["catalog"] = True
        dash = _http_json(f"http://{ip}:{CATALOG_PORT}/api/dashboard", timeout=1.5)
        extra = "Comparator / catalog UI on port 8767"
        if dash:
            extra += " (dashboard responding)"
        out["detail"] = (out["detail"] + " · " + extra).strip(" ·")
    return out


def neighbor_ips() -> list[str]:
    """Best-effort IPs from ARP / ip neigh (no extra privileges)."""
    cmds = (
        ["ip", "-4", "neigh", "show"],
        ["arp", "-n"],
        ["arp", "-a"],
    )
    text = ""
    for cmd in cmds:
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=4)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if proc.returncode == 0 and proc.stdout:
            text = proc.stdout
            break
    ips: list[str] = []
    me = lan_ip()
    for token in text.replace("(", " ").replace(")", " ").split():
        try:
            addr = ipaddress.ip_address(token)
        except ValueError:
            continue
        if addr.is_private and not addr.is_loopback and str(addr) != me:
            ips.append(str(addr))
    seen: set[str] = set()
    out: list[str] = []
    for ip in ips:
        if ip not in seen:
            seen.add(ip)
            out.append(ip)
    return out[:40]


def scan_lan(
    timeout: float = 0.3,
    limit: int = 250,
    *,
    quick: bool = False,
    include_self: bool = True,
) -> list[dict[str, Any]]:
    """Probe ARP neighbors and (unless quick) the /24 for 8766 / 8767."""
    ip = lan_ip()
    candidates: list[str] = []
    seen: set[str] = set()

    def add(host: str) -> None:
        if not host or host in seen or host.startswith("127."):
            return
        seen.add(host)
        candidates.append(host)

    for host in neighbor_ips():
        add(host)
    if not quick and not ip.startswith("127."):
        for host in subnet_hosts(ip)[:limit]:
            add(host)

    found: list[dict[str, Any]] = []
    found_ips: set[str] = set()

    if include_self:
        me = probe_host("127.0.0.1", timeout=max(timeout, 0.45))
        if me:
            me["this_machine"] = True
            public_ip = ip if not ip.startswith("127.") else "127.0.0.1"
            me["ip"] = public_ip
            if me.get("agent"):
                me["agent_url"] = f"http://{public_ip}:{AGENT_PORT}"
            found.append(me)
            found_ips.add(public_ip)
            found_ips.add("127.0.0.1")

    if candidates:
        with ThreadPoolExecutor(max_workers=64) as pool:
            futs = {pool.submit(probe_host, h, timeout): h for h in candidates}
            for fut in as_completed(futs):
                try:
                    hit = fut.result()
                except Exception:  # noqa: BLE001
                    continue
                if not hit:
                    continue
                if hit.get("ip") in found_ips:
                    continue
                found.append(hit)
                found_ips.add(str(hit.get("ip") or ""))

    found.sort(
        key=lambda r: (
            0 if r.get("this_machine") else 1,
            0 if r.get("agent") else 1,
            r.get("ip") or "",
        )
    )
    return found


def machine_snapshot() -> dict[str, Any]:
    ip = lan_ip()
    os_id = this_os()
    labels = {"windows": "Windows", "linux": "Linux", "mac": "macOS"}
    if os_id == "windows":
        suggested_role = "files"
        suggested_files = "this"
    else:
        suggested_role = "catalog"
        suggested_files = "windows"
    return {
        "os": os_id,
        "os_label": labels.get(os_id, os_id),
        "hostname": platform.node(),
        "arch": platform.machine(),
        "lan_ip": ip,
        "subnet": _subnet_label(ip),
        "agent_url": f"http://{ip}:{AGENT_PORT}",
        "catalog_url": f"http://127.0.0.1:{CATALOG_PORT}",
        "python": platform.python_version(),
        "suggested_role": suggested_role,
        "suggested_files_where": suggested_files,
    }


def _subnet_label(ip: str) -> str:
    try:
        net = ipaddress.ip_network(ip + "/24", strict=False)
    except ValueError:
        return ""
    return str(net)


def scan_network(*, quick: bool = False) -> dict[str, Any]:
    this = machine_snapshot()
    peers = scan_lan(quick=quick)
    return {
        "ok": True,
        "this": this,
        "peers": peers,
        "count": len(peers),
        "quick": quick,
        "neighbors": neighbor_ips() if quick else [],
    }


def recommend(
    *,
    role: str,
    files_where: str,
    this: dict[str, Any] | None = None,
    peers: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    role: catalog | files | both
    files_where: this | windows | linux | mixed
    """
    this = this or machine_snapshot()
    peers = peers or []
    os_id = this.get("os") or "linux"
    role = (role or "catalog").strip().lower()
    files_where = (files_where or "this").strip().lower()
    if role not in {"catalog", "files", "both"}:
        role = "catalog"
    if files_where not in {"this", "windows", "linux", "mixed"}:
        files_where = "this"

    agents = [p for p in peers if p.get("agent") and not p.get("this_machine")]
    catalogs = [p for p in peers if p.get("catalog") and not p.get("this_machine")]
    win_agents = [p for p in agents if "win" in str(p.get("agent_os") or "")]
    linux_agents = [
        p
        for p in agents
        if str(p.get("agent_os") or "").lower() in {"linux", "darwin"}
    ]

    suggested = ""
    if files_where == "windows" and win_agents:
        suggested = win_agents[0]["agent_url"]
    elif files_where == "linux" and linux_agents:
        suggested = linux_agents[0]["agent_url"]
    elif files_where in {"windows", "linux", "mixed"} and agents:
        suggested = agents[0]["agent_url"]
    elif files_where == "this" and role in {"files", "both"}:
        suggested = this.get("agent_url") or ""

    title, summary = _title_summary(os_id, role, files_where)
    here, other, then = _steps(os_id, role, files_where, this, suggested)

    needs_agent_here = role in {"files", "both"} and files_where in {"this", "mixed"}
    needs_comparator_here = role in {"catalog", "both"}
    if role == "catalog" and files_where in {"windows", "linux"}:
        needs_agent_here = False
    if role == "both" and files_where == "this":
        needs_agent_here = False
    if role == "files":
        needs_agent_here = True
        needs_comparator_here = False

    files_os = os_id if files_where == "this" else files_where
    return {
        "title": title,
        "summary": summary,
        "code": f"{os_id}-{role}-{files_where}",
        "pair": f"{os_id} catalog / {files_os} files"
        if role != "files"
        else f"{os_id} files / catalog on another PC",
        "this_machine": here,
        "other_machine": other,
        "then": then,
        "suggested_agent": suggested,
        "needs_agent_here": needs_agent_here,
        "needs_comparator_here": needs_comparator_here,
        "found_agents": agents,
        "found_catalogs": catalogs,
        "role": role,
        "files_where": files_where,
        "this_os": os_id,
    }


def _title_summary(os_id: str, role: str, files_where: str) -> tuple[str, str]:
    os_lab = {"windows": "Windows", "linux": "Linux", "mac": "Mac"}.get(os_id, os_id)
    if role == "both" and files_where == "this":
        return (
            f"Single {os_lab} machine",
            "The catalog app and the files are on this computer. No second-PC agent is required.",
        )
    if role == "catalog" and files_where == "windows":
        return (
            f"{os_lab} catalog + Windows file server",
            "Browse the library here. A small agent on the Windows PC lists unshared volumes such as D:/ and E:/.",
        )
    if role == "catalog" and files_where == "linux":
        return (
            f"{os_lab} catalog + Linux media server",
            "Browse here. Run the same agent on the Linux box that holds the disks.",
        )
    if role == "catalog" and files_where == "mixed":
        return (
            f"{os_lab} catalog + mixed file hosts",
            "Local folders on this PC, plus an agent on each machine that holds unshared disks.",
        )
    if role == "files":
        return (
            f"{os_lab} media host",
            "This machine holds the files. Install the agent here, then paste this address into Comparator on the catalog PC.",
        )
    if role == "both" and files_where == "windows":
        return (
            f"{os_lab} catalog, extra disks on Windows",
            "Run Comparator here for local files, and the Windows agent for disks that are not mounted.",
        )
    if role == "both" and files_where == "linux":
        return (
            f"{os_lab} catalog, extra disks on Linux",
            "Run Comparator here, and the agent on the Linux file server for unshared volumes.",
        )
    return (
        "Custom layout",
        "Use Comparator on the catalog PC and the media-host agent on every machine whose disks you cannot mount directly.",
    )


def _steps(
    os_id: str,
    role: str,
    files_where: str,
    this: dict[str, Any],
    suggested: str,
) -> tuple[list[str], list[str], list[str]]:
    here: list[str] = []
    other: list[str] = []
    then: list[str] = []
    ip = this.get("lan_ip") or "this-pc-ip"
    agent_here = f"http://{ip}:{AGENT_PORT}"

    if os_id == "windows":
        start_cmp = "On this PC: double-click run.bat in MultiMedia.Comparator (Python 3.9+)."
        start_host = "On this PC: double-click INSTALL.bat, then Set up this host. Click Yes on the firewall prompt."
    elif os_id == "mac":
        start_cmp = "On this Mac: cd MultiMedia.Comparator && ./run.sh  →  http://127.0.0.1:8767"
        start_host = "On this Mac: chmod +x INSTALL.sh && ./INSTALL.sh, then Set up this host. Allow incoming Python in Firewall if asked."
    else:
        start_cmp = "On this PC: cd MultiMedia.Comparator && ./run.sh  →  http://127.0.0.1:8767"
        start_host = "On this PC: chmod +x INSTALL.sh && ./INSTALL.sh, then Set up this host."

    win_host = (
        "On the Windows file PC: copy Media-Host-Setup, double-click INSTALL.bat, "
        "Set up this host, Yes on the firewall prompt, leave the agent window open."
    )
    linux_host = (
        "On the Linux file server: copy Media-Host-Setup, run ./INSTALL.sh, "
        "Set up this host (opens TCP 8766), leave the agent running."
    )

    if role == "both" and files_where == "this":
        here = [
            start_cmp,
            "Drives → Add local path for each library folder (or the whole disk).",
            "No second computer is required.",
        ]
        then = ["Find duplicates when the scan finishes."]
        return here, other, then

    if role == "catalog":
        here = [start_cmp]
        if files_where == "windows":
            other = [win_host]
            then = [
                f"Drives → Add media host → paste {suggested or 'http://WINDOWS-IP:8766'}",
                "List host drives, add each volume you care about, then Scan.",
            ]
        elif files_where == "linux":
            other = [linux_host]
            then = [
                f"Drives → Add media host → paste {suggested or 'http://LINUX-IP:8766'}",
                "List drives and scan.",
            ]
        elif files_where == "mixed":
            here.append("Add local folders for disks mounted on this PC.")
            other = [win_host, linux_host]
            then = ["Add each remote agent under Drives, then Scan."]
        else:
            here.append("Drives → Add local path.")
        return here, other, then

    if role == "files":
        here = [start_host, f"Copy this address onto the catalog PC: {agent_here}"]
        other = [
            "On the catalog PC (Linux, Windows, or Mac): run MultiMedia.Comparator, "
            f"Add drive → media host → paste {agent_here}."
        ]
        then = ["Scan each volume from the catalog PC. Leave this agent running."]
        return here, other, then

    here = [start_cmp, "Add local folders for anything mounted here."]
    if files_where == "windows":
        other = [win_host]
    elif files_where == "linux":
        other = [linux_host]
    else:
        other = [win_host, linux_host]
    then = [
        f"Add the remote agent ({suggested or 'http://FILE-SERVER-IP:8766'}) under Drives.",
        "Scan local and remote volumes, then Find duplicates.",
    ]
    return here, other, then
