# Contributing

Thanks for improving MultiMedia.Comparator.

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python3 -m unittest discover -s tests -v
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

## Publishing to GitHub

```bash
git add -A
git status    # confirm data/*.db, tools/, and .venv are absent
git commit -m "Initial public release"
gh repo create MultiMedia.Comparator --public --source=. --remote=origin --push
```

GitHub org: [wisdomdigitalmedia-sudo](https://github.com/wisdomdigitalmedia-sudo).

## Code notes

- `catalog.db` is the library of record (sibling Entertainment.Servers).
- Comparator binds `127.0.0.1:8767`. The agent binds `0.0.0.0:8766`.
- Extra-copy delete is two-step and path-confirmed; do not weaken that.
