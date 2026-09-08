"""HTTP client for the Windows Media Catalog agent."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import quote, urljoin

from scanner import normalize_windows_path_str, reclassify_item


class RemoteAgentError(Exception):
    pass


def _normalize_base(agent_url: str) -> str:
    url = agent_url.strip().rstrip("/")
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "http://" + url
    return url


def _request(
    agent_url: str,
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    token: str = "",
    timeout: float = 120.0,
) -> Any:
    base = _normalize_base(agent_url)
    url = urljoin(base + "/", path.lstrip("/"))
    data = None
    headers = {"Accept": "application/json"}
    if token:
        headers["X-Agent-Token"] = token
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            if not raw:
                return None
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(detail)
            detail = parsed.get("error") or detail
        except json.JSONDecodeError:
            pass
        raise RemoteAgentError(f"Agent HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RemoteAgentError(
            f"Cannot reach Windows agent at {base}: {exc.reason}. "
            "Is agent.py running on the media host? Is the firewall allowing the port?"
        ) from exc
    except TimeoutError as exc:
        raise RemoteAgentError(f"Timed out talking to agent at {base}") from exc


def health(agent_url: str, token: str = "") -> dict[str, Any]:
    return _request(agent_url, "GET", "/api/health", token=token, timeout=8)


def list_windows_drives(agent_url: str, token: str = "") -> list[dict[str, Any]]:
    data = _request(agent_url, "GET", "/api/drives", token=token, timeout=15)
    if not isinstance(data, dict) or "drives" not in data:
        raise RemoteAgentError("Unexpected response from agent /api/drives")
    drives = list(data["drives"])
    # Always expose HTML-safe paths (E:/) even if agent is an older build
    for d in drives:
        letter = (d.get("letter") or "").strip()
        if len(letter) >= 1 and letter[0].isalpha():
            safe = f"{letter[0].upper()}:/"
            d["path"] = safe
            d["letter"] = f"{letter[0].upper()}:"
        else:
            d["path"] = normalize_windows_path_str(d.get("path") or "")
    return drives


def scan_remote_path(
    agent_url: str, path: str, token: str = "", timeout: float = 3600.0
) -> list[dict[str, Any]]:
    cleaned = normalize_windows_path_str(path)
    data = _request(
        agent_url,
        "POST",
        "/api/scan",
        body={"path": cleaned},
        token=token,
        timeout=timeout,
    )
    if not isinstance(data, dict) or "items" not in data:
        raise RemoteAgentError("Unexpected response from agent /api/scan")
    # Reclassify on the catalog PC so "TV Shows" folders count as TV even if the
    # Windows agent is still running an older scanner.py
    return [reclassify_item(dict(item)) for item in data["items"]]


def probe_path(agent_url: str, path: str, token: str = "") -> dict[str, Any]:
    encoded = quote(path, safe="")
    return _request(
        agent_url,
        "GET",
        f"/api/path?path={encoded}",
        token=token,
        timeout=15,
    )


def ensure_remote_ffprobe(
    agent_url: str, token: str = "", force: bool = False, timeout: float = 240.0
) -> dict[str, Any]:
    """POST /api/ffprobe — install ffprobe on the Windows file host (agent 1.5+)."""
    data = _request(
        agent_url,
        "POST",
        "/api/ffprobe",
        body={"force": bool(force)},
        token=token,
        timeout=timeout,
    )
    if not isinstance(data, dict):
        raise RemoteAgentError("Unexpected response from agent /api/ffprobe")
    if not data.get("ok"):
        raise RemoteAgentError(data.get("detail") or "ffprobe install failed on file host")
    return data


def probe_remote_files(
    agent_url: str, paths: list[str], token: str = "", timeout: float = 180.0
) -> list[dict[str, Any]]:
    """POST /api/probe — stream info from agent 1.4+ (ffprobe)."""
    data = _request(
        agent_url,
        "POST",
        "/api/probe",
        body={"paths": list(paths)},
        token=token,
        timeout=timeout,
    )
    if not isinstance(data, dict) or "results" not in data:
        raise RemoteAgentError("Unexpected response from agent /api/probe")
    return list(data["results"])


def fetch_remote_smart(
    agent_url: str, path: str = "", token: str = ""
) -> dict[str, Any]:
    """GET /api/smart?path=E:/ — disk health from the Windows agent."""
    if path:
        encoded = quote(path, safe="")
        data = _request(
            agent_url,
            "GET",
            f"/api/smart?path={encoded}",
            token=token,
            timeout=90,
        )
    else:
        data = _request(
            agent_url, "GET", "/api/smart", token=token, timeout=90
        )
    if not isinstance(data, dict):
        raise RemoteAgentError("Unexpected SMART response from agent")
    return data
