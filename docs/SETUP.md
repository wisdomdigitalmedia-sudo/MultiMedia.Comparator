# Setup guide

This app is a **local catalog**. Clone it on the PC where you browse the library. If the media files live on another computer, also clone [Entertainment.Servers](https://github.com/wisdomdigitalmedia-sudo/Entertainment.Servers) (or download the host installer zip) onto that file host.

Keep the two repositories as siblings when you use both:

```text
your-workspace/
  MultiMedia.Comparator/     ← this repo (UI on port 8767)
  Entertainment.Servers/     ← agent, catalog.db, installer
```

## 1. Catalog PC (this app)

### Linux or macOS

```bash
git clone https://github.com/wisdomdigitalmedia-sudo/MultiMedia.Comparator.git
cd MultiMedia.Comparator
chmod +x run.sh
./run.sh
```

Creates a virtualenv, installs `requirements.txt`, and opens [http://127.0.0.1:8767](http://127.0.0.1:8767).

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

### If `catalog.db` is not next to this repo

```bash
export MMC_CATALOG_DB=/absolute/path/to/Entertainment.Servers/data/catalog.db
./run.sh
```

Windows (Command Prompt):

```bat
set MMC_CATALOG_DB=C:\path\to\Entertainment.Servers\data\catalog.db
run.bat
```

`catalog.db` is created on first use if it does not exist. It is local to your machine and is **not** in git.

## 2. Answer the setup questions

In the app, open **Setup**:

1. **This machine is** — catalog PC, file server, or both.
2. **The media files are on** — this computer, a Windows PC, a Linux PC / NAS, or mixed.

Click **Scan this network** (ports 8766 and 8767 on this subnet), then **Suggest install**. The page fills in an agent address when it finds one.

## 3. File host (only if disks are on another PC)

On the machine that holds the files:

1. From Comparator **Setup**, download **media-host-setup-1.6.zip**, or copy the Entertainment.Servers folder.
2. **Windows:** double-click `INSTALL.bat`. When Windows asks to allow changes, click **Yes** (the prompt may sit behind the browser). If the firewall step still fails, double-click `OPEN_FIREWALL.bat`.
3. **Linux or macOS:** `chmod +x INSTALL.sh && ./INSTALL.sh`.
4. Click **Set up this host**. Leave the agent window open.
5. Copy the address shown (`http://FILE-HOST-IP:8766`).

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

Same as above, but run `./INSTALL.sh` on the Linux file server and paste that host’s `http://LINUX-IP:8766`.

### Windows catalog + Windows file server

`run.bat` on the catalog PC; `INSTALL.bat` on the file PC.

### Single machine

Setup → “Both” + “This computer”. Add local paths only. No agent.

## 5. After drives are added

1. **Scan** each volume.
2. **Find duplicates**.
3. Optional **Deep scan** (needs `ffprobe` on the file host — the installer can put it there).
4. Delete extra copies only from a group after the two-step warning.

## 6. Updating the agent

Copy a new Entertainment.Servers tree (or a new installer zip) onto the file host, stop the old agent window, and run `INSTALL.bat` / `INSTALL.sh` again. Deep scan of remote files needs agent **1.5+**. Confirmed extra-copy delete needs agent **1.5.2**.

## 7. What is not in this repository

These stay on your disk only:

- `data/catalog.db` and `data/comparator.db` (your library)
- `tools/ffmpeg/` (downloaded `ffprobe`)
- `.venv/`
- Host-installer embedded Python (`host-installer/runtime/`)

Do not commit them. See `.gitignore`.

## Troubleshooting

| Symptom | Check |
|---|---|
| Setup scan finds nothing | Agent not running, or TCP 8766 blocked |
| “Could not reach agent” | Paste `http://FILE-HOST-IP:8766` (not 127.0.0.1 from the other PC) |
| Empty drive sizes | Agent offline; unknown sizes stay blank on purpose |
| Deep scan skipped on remote files | Upgrade the agent; click Install ffprobe on the host wizard |
| Catalog not found | Set `MMC_CATALOG_DB` or clone Entertainment.Servers as a sibling |
