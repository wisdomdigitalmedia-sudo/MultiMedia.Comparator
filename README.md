# MultiMedia.Comparator

Local web UI that finds duplicate movies, TV episodes, and tracks across your media folders, then **picks the best overall quality copy**.

One repository: catalog UI, `catalog.db`, media-host **agent**, and the click-and-run installer.

> Databases, downloaded `ffprobe` binaries, and virtualenvs are gitignored. Do not commit `data/*.db`.

## Features

- Add or remove local folders and remote volumes (Windows, Linux, or macOS file host)
- Scan for common video and audio containers
- Group the same title (normalized name + year, or show + `SxxExx`)
- Score copies: resolution, source, codec, HDR, audio, size vs expected bitrate
- Optional deep scan with `ffprobe` so filenames cannot beat a real remux
- Mark one **KEEP** per group; extra copies delete only after a two-step path confirmation
- Setup wizard that detects this OS, scans the LAN, and recommends the matching install

## Requirements

- Python 3.9+
- Optional: `ffmpeg` / `mediainfo` on the catalog PC for local deep scans

## Quick start

**Linux / macOS — catalog PC**

```bash
git clone https://github.com/wisdomdigitalmedia-sudo/MultiMedia.Comparator.git
cd MultiMedia.Comparator
chmod +x run.sh
./run.sh
```

**Windows — catalog PC**

1. Install [Python 3.9+](https://www.python.org/downloads/) and tick **Add python.exe to PATH**.
2. Clone this repository.
3. Double-click `run.bat`.

Open [http://127.0.0.1:8767](http://127.0.0.1:8767) → **Setup** → answer two questions → **Scan this network** → **Suggest install**.

**File host** (the PC that holds unshared disks): double-click `INSTALL.bat` (Windows) or run `./INSTALL.sh` (Linux/macOS). Same repo.

Full layouts and firewall: **[docs/SETUP.md](docs/SETUP.md)**.

## Layouts

| Catalog PC | File host | What to run |
|---|---|---|
| Linux | Windows | `./run.sh` here, `INSTALL.bat` on Windows |
| Linux | Linux / NAS | `./run.sh` here, `./INSTALL.sh` on the server |
| Windows | Windows | `run.bat` here, `INSTALL.bat` on the file PC |
| Windows | Linux | `run.bat` here, `./INSTALL.sh` on Linux |
| macOS | Windows or Linux | `./run.sh` here, installer on the disks |
| Any OS | Files on this PC | `./run.sh` / `run.bat` only — no agent |

## Repository layout

| Path | Role |
|---|---|
| `app.py` | Catalog UI (port 8767) |
| `media-host/agent.py` | File-host agent (port 8766) |
| `media-host/host-installer/` | Click-and-run wizard + zip pack |
| `data/` | Local `catalog.db` / `comparator.db` (not in git) |

## Configuration

| Variable | Purpose |
|---|---|
| `MMC_CATALOG_DB` | Absolute path to `catalog.db` if it is not under `data/` |
| `CATALOG_DB` | Same as `MMC_CATALOG_DB` |
| `MEDIA_CATALOG_AGENT_TOKEN` | Optional shared secret for the file-host agent |

## CLI

```bash
python3 cli.py catalog --limit 20
python3 cli.py import-catalog
python3 cli.py scan /mnt/media --name Movies
python3 cli.py compare --kind movie
python3 cli.py deep-scan
```

## Tests

```bash
python3 -m unittest discover -s tests -v
python3 -m unittest discover -s media-host/host-installer -v
```

## Safety

- Extra copies are deleted only after you confirm the exact path twice
- Removing a drive drops catalog rows only; files on disk stay put
- The UI binds to `127.0.0.1:8767` (this machine only)
- The file-host agent binds to `0.0.0.0:8766` on the LAN

## Documentation

- [Setup guide](docs/SETUP.md)
- [Contributing](CONTRIBUTING.md)
- [Security](SECURITY.md)
- [License](LICENSE)
