# MultiMedia.Comparator

Local web UI that finds duplicate movies, TV episodes, and tracks across your media folders, then **picks the best overall quality copy**.

This is the day-to-day catalog app: drives, free space, and duplicate ranking. It reads and writes `catalog.db` from the sibling [Entertainment.Servers](https://github.com/wisdomdigitalmedia-sudo/Entertainment.Servers) project. Unshared disks on another PC are reached through a small **media-host agent**.

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
- Sibling clone of **Entertainment.Servers** if you use a remote file host (agent + `catalog.db`)

## Quick start

**Linux / macOS**

```bash
git clone https://github.com/wisdomdigitalmedia-sudo/MultiMedia.Comparator.git
cd MultiMedia.Comparator
chmod +x run.sh
./run.sh
```

**Windows**

1. Install [Python 3.9+](https://www.python.org/downloads/) and tick **Add python.exe to PATH**.
2. Clone this repository.
3. Double-click `run.bat`.

Open [http://127.0.0.1:8767](http://127.0.0.1:8767) → **Setup** → answer two questions → **Scan this network** → **Suggest install**.

Full layouts, firewall, and agent steps: **[docs/SETUP.md](docs/SETUP.md)**.

## Layouts

| Catalog PC | File host | What to install |
|---|---|---|
| Linux | Windows | Comparator here, host installer on Windows |
| Linux | Linux / NAS | Comparator here, host installer on the server |
| Windows | Windows | `run.bat` here, `INSTALL.bat` on the file PC |
| Windows | Linux | `run.bat` here, `INSTALL.sh` on Linux |
| macOS | Windows or Linux | `./run.sh` here, host installer on the disks |
| Any OS | Files on this PC | Comparator only — no agent |

## Configuration

| Variable | Purpose |
|---|---|
| `MMC_CATALOG_DB` | Absolute path to `catalog.db` if it is not next to this repo |
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

## Related

[Entertainment.Servers](https://github.com/wisdomdigitalmedia-sudo/Entertainment.Servers) — media-host agent, `catalog.db`, and click-and-run installer (`media-host-setup-1.6.zip`).
