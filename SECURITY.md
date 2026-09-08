# Security

MultiMedia.Comparator is a **local** catalog. It is not a hosted service.

## What it exposes

| Process | Bind | Notes |
|---|---|---|
| Comparator UI | `127.0.0.1:8767` | This machine only |
| Media-host agent | `0.0.0.0:8766` | LAN. Optional `MEDIA_CATALOG_AGENT_TOKEN` / `--token` |

The agent can list drives, scan media paths, run `ffprobe`, and delete a file after Comparator sends a confirmed extra-copy path. Run it only on a trusted LAN. Prefer a token if the network is shared.

## What is not collected

No telemetry, accounts, or cloud upload. Library metadata stays in local SQLite files that are gitignored.

## Reporting

Please open a GitHub issue for vulnerabilities. Do not attach `catalog.db`, file lists, or screenshots that show personal paths.
