"""Ask the Entertainment.Servers Windows agent to ffprobe remote files."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urljoin


class RemoteProbeError(Exception):
    pass


def _normalize_base(agent_url: str) -> str:
    url = (agent_url or "").strip().rstrip("/")
    if url and not url.startswith("http://") and not url.startswith("https://"):
        url = "http://" + url
    return url


def ensure_remote_ffprobe(
    agent_url: str,
    token: str = "",
    force: bool = False,
    timeout: float = 240.0,
) -> dict[str, Any]:
    """POST /api/ffprobe  { "force": bool } — agent 1.5+ installs ffprobe on the file host."""
    base = _normalize_base(agent_url)
    if not base:
        raise RemoteProbeError("agent URL is empty")
    url = urljoin(base + "/", "api/ffprobe")
    body = json.dumps({"force": bool(force)}).encode("utf-8")
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if token:
        headers["X-Agent-Token"] = token
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            data = json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        if exc.code == 404:
            raise RemoteProbeError(
                "Windows agent has no /api/ffprobe (need agent 1.5+). "
                "Copy the updated agent.py to the media host and restart it."
            ) from exc
        raise RemoteProbeError(f"Agent HTTP {exc.code}: {detail[:300]}") from exc
    except urllib.error.URLError as exc:
        raise RemoteProbeError(f"Cannot reach agent at {base}: {exc.reason}") from exc
    except TimeoutError as exc:
        raise RemoteProbeError(f"Timed out installing ffprobe at {base}") from exc
    except json.JSONDecodeError as exc:
        raise RemoteProbeError("Agent returned non-JSON") from exc
    if not isinstance(data, dict):
        raise RemoteProbeError("Unexpected ffprobe-install response")
    if not data.get("ok"):
        raise RemoteProbeError(data.get("detail") or "ffprobe install failed on file host")
    return data


def probe_remote_files(
    agent_url: str,
    paths: list[str],
    token: str = "",
    timeout: float = 180.0,
) -> list[dict[str, Any]]:
    """
    POST /api/probe  { "paths": [...] }

    Works with Entertainment.Servers agent 1.4.0+. Older agents raise
    RemoteProbeError with a clear upgrade message.
    """
    base = _normalize_base(agent_url)
    if not base:
        raise RemoteProbeError("agent URL is empty")
    url = urljoin(base + "/", "api/probe")
    body = json.dumps({"paths": list(paths)}).encode("utf-8")
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if token:
        headers["X-Agent-Token"] = token
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            data = json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        if exc.code == 404:
            raise RemoteProbeError(
                "Windows agent has no /api/probe (need agent 1.4.0+). "
                "Copy the updated agent.py to the media host and restart it."
            ) from exc
        raise RemoteProbeError(f"Agent HTTP {exc.code}: {detail[:300]}") from exc
    except urllib.error.URLError as exc:
        raise RemoteProbeError(f"Cannot reach agent at {base}: {exc.reason}") from exc
    except TimeoutError as exc:
        raise RemoteProbeError(f"Timed out talking to agent at {base}") from exc
    except json.JSONDecodeError as exc:
        raise RemoteProbeError("Agent returned non-JSON") from exc

    if not isinstance(data, dict):
        raise RemoteProbeError("Unexpected probe response")
    results = data.get("results")
    if not isinstance(results, list):
        raise RemoteProbeError("Unexpected probe response (no results)")
    return list(results)


def agent_health(
    agent_url: str,
    token: str = "",
    timeout: float = 8.0,
) -> dict[str, Any]:
    """GET /api/health."""
    base = _normalize_base(agent_url)
    if not base:
        raise RemoteProbeError("agent URL is empty")
    url = urljoin(base + "/", "api/health")
    headers = {"Accept": "application/json"}
    if token:
        headers["X-Agent-Token"] = token
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            data = json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RemoteProbeError(f"Agent HTTP {exc.code}: {detail[:300]}") from exc
    except urllib.error.URLError as exc:
        raise RemoteProbeError(f"Cannot reach agent at {base}: {exc.reason}") from exc
    except TimeoutError as exc:
        raise RemoteProbeError(f"Timed out talking to agent at {base}") from exc
    except json.JSONDecodeError as exc:
        raise RemoteProbeError("Agent returned non-JSON") from exc
    if not isinstance(data, dict):
        raise RemoteProbeError("Unexpected /api/health response")
    return data


def scan_remote_path(
    agent_url: str,
    path: str,
    token: str = "",
    timeout: float = 3600.0,
) -> list[dict[str, Any]]:
    """POST /api/scan {path} — inventory media on the file host."""
    base = _normalize_base(agent_url)
    if not base:
        raise RemoteProbeError("agent URL is empty")
    url = urljoin(base + "/", "api/scan")
    body = json.dumps({"path": path}).encode("utf-8")
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if token:
        headers["X-Agent-Token"] = token
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            data = json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RemoteProbeError(f"Agent HTTP {exc.code}: {detail[:300]}") from exc
    except urllib.error.URLError as exc:
        raise RemoteProbeError(f"Cannot reach agent at {base}: {exc.reason}") from exc
    except TimeoutError as exc:
        raise RemoteProbeError(f"Timed out scanning {path} at {base}") from exc
    except json.JSONDecodeError as exc:
        raise RemoteProbeError("Agent returned non-JSON") from exc
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise RemoteProbeError("Unexpected /api/scan response")
    return list(data["items"])


def list_agent_drives(
    agent_url: str,
    token: str = "",
    timeout: float = 45.0,
) -> list[dict[str, Any]]:
    """GET /api/drives — letters plus total/free/used bytes from the file host."""
    base = _normalize_base(agent_url)
    if not base:
        raise RemoteProbeError("agent URL is empty")
    url = urljoin(base + "/", "api/drives")
    headers = {"Accept": "application/json"}
    if token:
        headers["X-Agent-Token"] = token
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            data = json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RemoteProbeError(f"Agent HTTP {exc.code}: {detail[:300]}") from exc
    except urllib.error.URLError as exc:
        raise RemoteProbeError(f"Cannot reach agent at {base}: {exc.reason}") from exc
    except TimeoutError as exc:
        raise RemoteProbeError(f"Timed out listing drives at {base}") from exc
    except json.JSONDecodeError as exc:
        raise RemoteProbeError("Agent returned non-JSON") from exc
    if not isinstance(data, dict):
        raise RemoteProbeError("Unexpected /api/drives response")
    drives = data.get("drives")
    if not isinstance(drives, list):
        raise RemoteProbeError("Unexpected /api/drives response (no drives)")
    return list(drives)


def delete_remote_file(
    agent_url: str,
    path: str,
    token: str = "",
    timeout: float = 60.0,
) -> dict[str, Any]:
    """POST /api/delete {path} — agent 1.5.2+ unlinks one media file."""
    base = _normalize_base(agent_url)
    if not base:
        raise RemoteProbeError("agent URL is empty")
    url = urljoin(base + "/", "api/delete")
    body = json.dumps({"path": path}).encode("utf-8")
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if token:
        headers["X-Agent-Token"] = token
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            data = json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        if exc.code == 404:
            raise RemoteProbeError(
                "Windows agent has no /api/delete (need agent 1.5.2+). "
                "Copy the updated agent.py to the media host and restart it."
            ) from exc
        try:
            data = json.loads(detail) if detail else {}
        except json.JSONDecodeError:
            raise RemoteProbeError(f"Agent HTTP {exc.code}: {detail[:300]}") from exc
        if isinstance(data, dict) and data.get("error"):
            raise RemoteProbeError(str(data.get("error")))
        raise RemoteProbeError(f"Agent HTTP {exc.code}: {detail[:300]}") from exc
    except urllib.error.URLError as exc:
        raise RemoteProbeError(f"Cannot reach agent at {base}: {exc.reason}") from exc
    except TimeoutError as exc:
        raise RemoteProbeError(f"Timed out deleting at {base}") from exc
    except json.JSONDecodeError as exc:
        raise RemoteProbeError("Agent returned non-JSON") from exc
    if not isinstance(data, dict):
        raise RemoteProbeError("Unexpected /api/delete response")
    if not data.get("ok"):
        raise RemoteProbeError(data.get("error") or "Delete failed on file host")
    return data
