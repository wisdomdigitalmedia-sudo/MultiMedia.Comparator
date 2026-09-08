"""Build the click-and-run Media Host setup zip."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

ROOT_FILES = (
    "agent.py",
    "scanner.py",
    "config.py",
    "smart_health.py",
    "crystaldisk.py",
    "run_agent.bat",
    "RUN_AGENT_AS_ADMIN.bat",
    "OPEN_FIREWALL.bat",
    "INSTALL.bat",
    "INSTALL.sh",
    "README.md",
)

INSTALLER_FILES = (
    "INSTALL.bat",
    "INSTALL.sh",
    "bootstrap.ps1",
    "open-firewall.ps1",
    "wizard.py",
    "topology.py",
    "deps.py",
    "pack.py",
    "static/style.css",
    "templates/wizard.html",
    "README.txt",
)


def build_zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in ROOT_FILES:
            path = REPO / name
            if path.is_file():
                zf.write(path, arcname=name)
        for name in INSTALLER_FILES:
            path = REPO / "host-installer" / name
            if path.is_file():
                zf.write(path, arcname=f"host-installer/{name}")
        zf.writestr(
            "START_HERE.txt",
            (
                "Media Host setup v1.6\r\n"
                "\r\n"
                "Answer two questions (catalog PC vs file server, Windows vs Linux).\r\n"
                "The page scans the LAN and tells you what to install where.\r\n"
                "\r\n"
                "WINDOWS\r\n"
                "  Double-click INSTALL.bat\r\n"
                "  Your browser opens. Pick your layout, then Set up this host.\r\n"
                "  When Windows asks to allow changes, click Yes\r\n"
                "  (that prompt may sit behind the browser).\r\n"
                "  If the firewall step still fails, double-click OPEN_FIREWALL.bat\r\n"
                "  and click Yes on the prompt.\r\n"
                "\r\n"
                "LINUX media server\r\n"
                "  chmod +x INSTALL.sh && ./INSTALL.sh\r\n"
                "  Same page. Click Set up this host.\r\n"
                "\r\n"
                "Then on the catalog PC: Add drive → media host → paste the address shown.\r\n"
            ),
        )
    return buf.getvalue()
