# media-host

File-host half of **MultiMedia.Comparator**: the agent, `catalog.db`, and click-and-run installer.

This folder is not a separate project. Clone [MultiMedia.Comparator](https://github.com/wisdomdigitalmedia-sudo/MultiMedia.Comparator) and:

- **Catalog PC:** `./run.sh` or `run.bat` at the repo root
- **File host:** `INSTALL.bat` / `INSTALL.sh` at the repo root (they call this folder)

Agent API (port 8766): `/api/health`, `/api/drives`, `/api/scan`, `/api/probe`, `/api/delete`.
