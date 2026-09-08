# Setup guide

One clone covers the catalog PC and the file host.

```text
MultiMedia.Comparator/
  run.sh / run.bat          ← catalog UI (port 8767)
  INSTALL.sh / INSTALL.bat  ← file-host agent wizard
  media-host/               ← agent, catalog store, installer pack
  data/                     ← catalog.db (created locally, not in git)
```

## 1. Catalog PC

### Linux or macOS

```bash
git clone https://github.com/wisdomdigitalmedia-sudo/MultiMedia.Comparator.git
cd MultiMedia.Comparator
chmod +x run.sh
./run.sh
```

Optional local deep scan:

```bash
# Debian / Ubuntu
sudo apt install ffmpeg mediainfo
```

```bash
# macOS
brew install ffmpeg mediainfo
```

### Windows

1. Install Python 3.9+ from [python.org](https://www.python.org/downloads/). Check **Add python.exe to PATH**.
2. Clone this repository.
3. Double-click `run.bat`.

### If `catalog.db` is somewhere else

```bash
export MMC_CATALOG_DB=/absolute/path/to/catalog.db
./run.sh
```

Windows (Command Prompt):

```bat
set MMC_CATALOG_DB=C:\path\to\catalog.db
run.bat
```

`catalog.db` is created on first use under `data/` if it does not exist. It is **not** in git.

## 2. Answer the setup questions

In the app, open **Setup**:

1. **This machine is** — catalog PC, file server, or both.
2. **The media files are on** — this computer, a Windows PC, a Linux PC / NAS, or mixed.

Click **Scan this network** (ports 8766 and 8767 on this subnet), then **Suggest install**. The page fills in an agent address when it finds one.

## 3. File host (only if disks are on another PC)

On the machine that holds the files, clone or copy **this same repository**:

1. **Windows:** double-click `INSTALL.bat`. When Windows asks to allow changes, click **Yes** (the prompt may sit behind the browser). If the firewall step still fails, double-click `media-host/OPEN_FIREWALL.bat`.
2. **Linux or macOS:** `chmod +x INSTALL.sh && ./INSTALL.sh`.
3. Click **Set up this host**. Leave the agent window open.
4. Copy the address shown (`http://FILE-HOST-IP:8766`).

Or from the catalog PC **Setup** page, download **media-host-setup-1.6.zip** and unzip it on the file host.

Then on the catalog PC: **Drives → Add media host → paste the address → List host drives → Add → Scan**.

### Firewall

| OS | Port | Action |
|---|---|---|
| Windows | TCP 8766 inbound | Installer UAC prompt, or `OPEN_FIREWALL.bat` |
| Linux | TCP 8766 | Installer runs `ufw allow 8766/tcp` when ufw is present |
| macOS | TCP 8766 | System Settings → Network → Firewall → allow Python |

The Comparator UI stays on `127.0.0.1:8767` and does not need a LAN firewall rule.

## 4. Example layouts

### Linux catalog + Windows file server

1. Catalog PC: `./run.sh` → Setup → “catalog PC” + “a Windows PC”.
2. Windows PC: `INSTALL.bat` → Set up this host → Yes on the firewall prompt.
3. Catalog PC: paste `http://WINDOWS-IP:8766` under Drives.

### Linux catalog + Linux media server

Same as above, but run `./INSTALL.sh` on the Linux file server.

### Single machine

Setup → “Both” + “This computer”. Add local paths only. No agent.

## 5. After drives are added

1. **Scan** each volume.
2. **Find duplicates**.
3. Optional **Deep scan** (needs `ffprobe` on the file host — the installer can put it there).
4. Delete extra copies only from a group after the two-step warning.

## 6. Updating the agent

Copy a new clone (or a new installer zip) onto the file host, stop the old agent window, and run `INSTALL.bat` / `INSTALL.sh` again. Deep scan of remote files needs agent **1.5+**. Confirmed extra-copy delete needs agent **1.5.2**.

## 7. What is not in this repository

These stay on your disk only:

- `data/catalog.db` and `data/comparator.db` (your library)
- `tools/ffmpeg/` (downloaded `ffprobe`)
- `.venv/`
- `media-host/host-installer/runtime/` (embedded Python on Windows)

## Troubleshooting

| Symptom | Check |
|---|---|
| Setup scan finds nothing | Agent not running, or TCP 8766 blocked |
| “Could not reach agent” | Paste `http://FILE-HOST-IP:8766` (not 127.0.0.1 from the other PC) |
| Empty drive sizes | Agent offline; unknown sizes stay blank on purpose |
| Deep scan skipped on remote files | Upgrade the agent; click Install ffprobe on the host wizard |
| Catalog not found | Set `MMC_CATALOG_DB` or add a drive so `data/catalog.db` is created |
