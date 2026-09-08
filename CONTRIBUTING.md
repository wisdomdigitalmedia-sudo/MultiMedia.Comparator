# Contributing

Thanks for improving MultiMedia.Comparator.

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python3 -m unittest discover -s tests -v
python3 -m unittest discover -s media-host/host-installer -v
./run.sh                    # Windows: run.bat
```

The UI is Flask templates + `static/`. Keep the dark / teal Comparator look.

## Pull requests

- Keep diffs scoped to the change.
- Add or update tests when behavior changes.
- Do **not** commit:
  - `data/*.db` or any personal catalog
  - `tools/` binaries
  - `.venv/`
  - real hostnames, LAN IPs, usernames, or drive labels from a home library
- Use documentation IPs (`192.0.2.0/24` or `192.168.1.50`) and generic names (`External D`, `NAS media`) in tests and placeholders.

GitHub: [wisdomdigitalmedia-sudo/MultiMedia.Comparator](https://github.com/wisdomdigitalmedia-sudo/MultiMedia.Comparator).

## Code notes

- `catalog.db` is the library of record (`data/catalog.db`, or a legacy Entertainment.Servers path).
- File-host agent and installer live in `media-host/`.
- Comparator binds `127.0.0.1:8767`. The agent binds `0.0.0.0:8766`.
- Extra-copy delete is two-step and path-confirmed; do not weaken that.
