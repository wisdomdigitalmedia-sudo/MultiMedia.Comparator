#!/usr/bin/env python3
"""Click-and-run Media Host setup wizard (Windows or Linux)."""

from __future__ import annotations

import json
import sys
import threading
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from deps import host_status, run_step  # noqa: E402
from topology import machine_snapshot, recommend, scan_lan  # noqa: E402

WIZARD_HOST = "127.0.0.1"
WIZARD_PORT = 8768


def _read(path: Path) -> bytes:
    return path.read_bytes()


class WizardHandler(BaseHTTPRequestHandler):
    server_version = "MediaHostSetup/1.6"

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status: int, payload: object) -> None:
        raw = json.dumps(payload).encode("utf-8")
        self._send(status, raw, "application/json; charset=utf-8")

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        try:
            if path == "/":
                html = HERE / "templates" / "wizard.html"
                self._send(200, _read(html), "text/html; charset=utf-8")
                return
            if path == "/static/style.css":
                css = HERE / "static" / "style.css"
                self._send(200, _read(css), "text/css; charset=utf-8")
                return
            if path == "/api/status":
                self._send_json(200, host_status())
                return
            if path == "/api/machine":
                self._send_json(200, machine_snapshot())
                return
            if path == "/api/lan-scan":
                qs = parse_qs(parsed.query)
                quick = (qs.get("quick") or ["0"])[0].lower() in {"1", "true", "yes"}
                peers = scan_lan(quick=quick)
                self._send_json(
                    200,
                    {"ok": True, "peers": peers, "count": len(peers), "quick": quick},
                )
                return
            self._send(404, b'{"error":"not found"}', "application/json")
        except Exception as exc:  # noqa: BLE001
            self._send_json(500, {"error": str(exc), "trace": traceback.format_exc()})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        try:
            if path == "/api/plan":
                body = self._read_json()
                plan = recommend(
                    role=str(body.get("role") or "catalog"),
                    files_where=str(body.get("files_where") or "this"),
                    this=machine_snapshot(),
                    peers=list(body.get("peers") or []),
                )
                self._send_json(200, plan)
                return
            if path == "/api/setup":
                body = self._read_json()
                step = str(body.get("step") or "")
                force = bool(body.get("force"))
                result = run_step(step, force=force)
                result["status"] = host_status()
                self._send_json(200 if result.get("ok") else 500, result)
                return
            if path == "/api/setup-all":
                body = self._read_json()
                force = bool(body.get("force"))
                steps = body.get("steps") or ["ffprobe", "smart", "firewall", "agent"]
                results = []
                ok = True
                for step in steps:
                    item = run_step(str(step), force=force)
                    item["step"] = step
                    results.append(item)
                    if not item.get("ok"):
                        ok = False
                self._send_json(
                    200 if ok else 207,
                    {"ok": ok, "results": results, "status": host_status()},
                )
                return
            self._send(404, b'{"error":"not found"}', "application/json")
        except Exception as exc:  # noqa: BLE001
            self._send_json(500, {"error": str(exc), "trace": traceback.format_exc()})


def main() -> None:
    httpd = ThreadingHTTPServer((WIZARD_HOST, WIZARD_PORT), WizardHandler)
    url = f"http://{WIZARD_HOST}:{WIZARD_PORT}/"
    print(f"Media Host setup → {url}")
    print("Leave this window open until setup finishes. Then start the agent from the page.")
    threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nSetup wizard stopped.")
        httpd.server_close()


if __name__ == "__main__":
    main()
