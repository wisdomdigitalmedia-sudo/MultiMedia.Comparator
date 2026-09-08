#!/usr/bin/env python3
"""Command-line interface for MultiMedia.Comparator."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow `python cli.py` from the project root
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mmc.integration import compare_catalog  # noqa: E402
from mmc.pipeline import (  # noqa: E402
    compare_loaded,
    deep_scan_paths,
    import_entertainment_catalog,
    import_folder,
)
from mmc.scanner import format_size  # noqa: E402


def _print_groups(groups, limit: int = 25) -> None:
    print(f"{len(groups)} duplicate group(s)\n")
    for g in groups[:limit]:
        print(f"== {g.label}  ({g.kind}, {len(g.copies)} copies, gap {g.score_gap})")
        for c in g.copies:
            mark = "*" if c.is_winner else " "
            size = format_size(c.item.get("size_bytes") or 0)
            drive = c.item.get("drive_name") or ""
            print(
                f"  {mark} {c.score.total:5.1f}  {c.score.summary:40s}  {size:>8}  "
                f"{drive}  {c.item.get('file_name')}"
            )
        print()
    if len(groups) > limit:
        print(f"… {len(groups) - limit} more groups")


def main() -> int:
    parser = argparse.ArgumentParser(description="Find duplicate media and pick the best copy")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_imp = sub.add_parser("import-catalog", help="Import catalog.db into the comparator store")
    p_imp.add_argument("--catalog", default=None)

    p_fold = sub.add_parser("scan", help="Scan a local folder")
    p_fold.add_argument("path")
    p_fold.add_argument("--name", default="")

    p_cmp = sub.add_parser("compare", help="Group loaded items and rank copies")
    p_cmp.add_argument("--kind", default=None)
    p_cmp.add_argument("--limit", type=int, default=25)
    p_cmp.add_argument("--json", action="store_true")

    p_live = sub.add_parser("catalog", help="Compare catalog.db directly")
    p_live.add_argument("--catalog", default=None)
    p_live.add_argument("--kind", default=None)
    p_live.add_argument("--limit", type=int, default=25)
    p_live.add_argument("--json", action="store_true")

    p_deep = sub.add_parser("deep-scan", help="ffprobe files in current duplicate groups")
    p_deep.add_argument("--no-remote", action="store_true")

    p_ff = sub.add_parser("ensure-ffprobe", help="Install ffprobe on this machine if missing")
    p_ff.add_argument("--force", action="store_true", help="Re-download even if ffprobe exists")

    args = parser.parse_args()

    if args.cmd == "import-catalog":
        sid, count = import_entertainment_catalog(args.catalog)
        print(f"Imported {count} items (source {sid})")
        return 0
    if args.cmd == "scan":
        sid, count = import_folder(args.path, name=args.name)
        print(f"Scanned {count} items (source {sid})")
        return 0
    if args.cmd == "compare":
        groups = compare_loaded(kind=args.kind)
        if args.json:
            from mmc.grouper import groups_to_jsonable

            print(json.dumps(groups_to_jsonable(groups), indent=2))
        else:
            _print_groups(groups, limit=args.limit)
        return 0
    if args.cmd == "catalog":
        result = compare_catalog(args.catalog, kind=args.kind)
        if args.json:
            print(json.dumps(result.as_dict(), indent=2)[:50000])
        else:
            print(
                f"{result.item_count} items → {result.group_count} groups, "
                f"{result.extra_copies} extras"
            )
            for n in result.notes:
                print("note:", n)
            _print_groups(result.groups, limit=args.limit)
        return 0
    if args.cmd == "deep-scan":
        groups = compare_loaded()
        items = [c.item for g in groups for c in g.copies]
        probes = deep_scan_paths(items, remote=not args.no_remote)
        groups = compare_loaded(probes=probes)
        ok = sum(1 for p in probes.values() if p.ok)
        print(f"Probed {ok}/{len(probes)}")
        _print_groups(groups, limit=20)
        return 0
    if args.cmd == "ensure-ffprobe":
        from mmc.ffprobe_install import FfprobeInstallError, install_ffprobe

        try:
            report = install_ffprobe(force=args.force)
        except FfprobeInstallError as exc:
            print(f"ffprobe install failed: {exc}")
            return 1
        print(
            f"ffprobe {'installed' if report.get('installed') else 'ready'} "
            f"({report.get('source')}): {report.get('path')}"
        )
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
