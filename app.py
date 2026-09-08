#!/usr/bin/env python3
"""Media Comparator — local web UI."""

from __future__ import annotations

import csv
import io
import json
import sys
from pathlib import Path
from urllib.parse import unquote

from flask import (
    Flask,
    Response,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from mmc import db
from mmc.catalog_store import (
    fold_by_depth,
    get_default_agent,
    get_drive,
    list_media,
    max_folder_depth,
    path_parts,
)
from mmc.config import HOST, PORT, SECRET_KEY, find_catalog_db
from mmc.dashboard import build_dashboard, enrich_drive, load_drive_cards
from mmc.drive_ops import (
    DriveOpsError,
    add_local_drive,
    add_remote_drive,
    list_windows_volumes,
    remove_drive,
    scan_drive as scan_catalog_drive,
    sync_comparator_library,
)
from mmc.file_delete import (
    DeleteError,
    delete_copy_file,
    drop_copy_from_groups,
    find_copy,
    forget_copy,
)
from mmc.grouper import DuplicateGroup
from mmc.pipeline import (
    compare_loaded,
    deep_scan_paths,
    import_entertainment_catalog,
    stats as pipeline_stats,
)
from mmc.remote_probe import RemoteProbeError
from mmc.scanner import format_size

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.jinja_env.filters["filesize"] = format_size

_STATIC_DIR = Path(__file__).resolve().parent / "static"
_CACHE: dict[str, list[DuplicateGroup]] = {"groups": []}


@app.context_processor
def _inject_chrome() -> dict:
    css = _STATIC_DIR / "style.css"
    js = _STATIC_DIR / "dashboard.js"
    adv = _STATIC_DIR / "groups-advanced.js"
    try:
        css_v = int(css.stat().st_mtime)
    except OSError:
        css_v = 0
    try:
        js_v = int(js.stat().st_mtime)
    except OSError:
        js_v = 0
    try:
        adv_v = int(adv.stat().st_mtime)
    except OSError:
        adv_v = 0
    return {"css_v": css_v, "js_v": js_v, "adv_v": adv_v, "nav": request.endpoint or ""}


@app.before_request
def _init() -> None:
    db.init_db()


def _groups() -> list[DuplicateGroup]:
    """In-memory only. Rebuilding 100k+ identities on every GET is a hang, not a load."""
    return list(_CACHE["groups"] or [])


def _store_groups(groups: list[DuplicateGroup]) -> None:
    _CACHE["groups"] = groups
    summary = {
        "group_count": len(groups),
        "extra_copies": sum(max(0, len(g.copies) - 1) for g in groups),
        "item_hint": pipeline_stats().get("item_count") or 0,
    }
    db.set_setting("last_compare_meta", json.dumps(summary))
    db.set_setting("last_compare_json", "1")


def _meta() -> dict:
    raw = db.get_setting("last_compare_meta")
    if not raw:
        return {"group_count": len(_CACHE["groups"]), "extra_copies": 0}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"group_count": 0, "extra_copies": 0}


def _has_compare() -> bool:
    return bool(_CACHE["groups"] or db.get_setting("last_compare_json"))


def _clear_compare() -> None:
    _CACHE["groups"] = []
    db.set_setting("last_compare_json", "")


def _sync_library() -> None:
    _clear_compare()
    sync_comparator_library()


@app.route("/")
def index():
    dash = build_dashboard(fill_unknown=True, fill_remote=False)
    meta = _meta()
    empty_start = [
        {"href": url_for("setup_page"), "label": "Setup wizard", "class": "primary"},
        {"href": url_for("add_drive", source="remote"), "label": "Add a media host", "class": "ghost"},
    ]
    empty_nosize = [
        {"href": url_for("sources_page"), "label": "Manage drives", "class": "ghost"},
    ]
    return render_template(
        "index.html",
        dash=dash,
        space=dash["space"],
        library=dash["library"],
        tightest=dash["tightest"],
        group_count=meta.get("group_count") or 0,
        extra_copies=meta.get("extra_copies") or 0,
        dash_json=json.dumps(dash),
        empty_start=empty_start,
        empty_nosize=empty_nosize,
    )


@app.route("/api/dashboard")
def api_dashboard():
    fill_remote = request.args.get("fill", "").strip().lower() in {"1", "true", "yes"}
    payload = build_dashboard(fill_unknown=True, fill_remote=fill_remote)
    payload["groups"] = _meta()
    return Response(json.dumps(payload), mimetype="application/json")


@app.route("/sources")
@app.route("/drives")
def sources_page():
    empty_drives = [
        {"href": url_for("setup_page"), "label": "Setup wizard", "class": "primary"},
        {"href": url_for("add_drive", source="remote"), "label": "Add a media host", "class": "ghost"},
    ]
    return render_template(
        "drives.html",
        drives=load_drive_cards(),
        catalog_path=find_catalog_db(),
        empty_drives=empty_drives,
    )


@app.route("/drives/add", methods=["GET", "POST"])
def add_drive():
    source = request.values.get("source", "local").strip().lower()
    if source not in {"local", "remote"}:
        source = "local"
    defaults = {}
    try:
        defaults = get_default_agent()
    except FileNotFoundError:
        defaults = {}

    if request.method == "POST":
        form_state = {
            "name": request.form.get("name", "").strip(),
            "root_path": request.form.get("root_path", "").strip(),
            "notes": request.form.get("notes", "").strip(),
            "agent_url": request.form.get("agent_url", "").strip(),
            "agent_token": request.form.get("agent_token", "").strip(),
            "agent_host": request.form.get("agent_host", "").strip(),
            "agent_port": request.form.get("agent_port", "8766").strip() or "8766",
        }
    else:
        form_state = {
            "name": "",
            "root_path": "",
            "notes": "",
            "agent_url": defaults.get("agent_url") or "",
            "agent_token": defaults.get("agent_token") or "",
            "agent_host": defaults.get("agent_host") or "",
            "agent_port": defaults.get("agent_port") or "8766",
        }

    remote_drives: list = []
    agent_info: dict | None = None
    action = request.form.get("action", "save") if request.method == "POST" else ""

    if request.method == "POST" and action == "list_remote":
        url = form_state["agent_url"]
        if not url and form_state["agent_host"]:
            url = f"http://{form_state['agent_host']}:{form_state['agent_port']}"
            form_state["agent_url"] = url
        try:
            agent_info, remote_drives = list_windows_volumes(
                url, token=form_state["agent_token"]
            )
            flash(
                f"Connected to {agent_info.get('hostname', 'media host')} — "
                f"{len(remote_drives)} drive(s) found.",
                "ok",
            )
        except RemoteProbeError as exc:
            flash(str(exc), "error")
        return render_template(
            "drive_add.html",
            source=source,
            form=form_state,
            remote_drives=remote_drives,
            agent_info=agent_info,
        )

    if request.method == "POST" and action == "save":
        name = form_state["name"]
        root_path = form_state["root_path"]
        if not name or not root_path:
            flash("Name and path are required.", "error")
            return render_template(
                "drive_add.html",
                source=source,
                form=form_state,
                remote_drives=remote_drives,
                agent_info=agent_info,
            )
        try:
            if source == "local":
                drive_id = add_local_drive(name, root_path, notes=form_state["notes"])
            else:
                drive_id = add_remote_drive(
                    name,
                    root_path,
                    agent_url=form_state["agent_url"],
                    agent_token=form_state["agent_token"],
                    agent_host=form_state["agent_host"],
                    agent_port=form_state["agent_port"],
                    notes=form_state["notes"],
                )
            _sync_library()
            flash(f"Drive “{name}” added (#{drive_id}). Scan when you want titles indexed.", "ok")
            return redirect(url_for("sources_page"))
        except (DriveOpsError, ValueError, FileNotFoundError) as exc:
            flash(str(exc), "error")
            return render_template(
                "drive_add.html",
                source=source,
                form=form_state,
                remote_drives=remote_drives,
                agent_info=agent_info,
            )

    return render_template(
        "drive_add.html",
        source=source,
        form=form_state,
        remote_drives=remote_drives,
        agent_info=agent_info,
    )


@app.route("/drives/<int:drive_id>/delete", methods=["POST"])
def delete_drive(drive_id: int):
    try:
        name = remove_drive(drive_id)
        _sync_library()
        flash(f"Removed “{name}” from the catalog. Files on disk were not touched.", "ok")
    except DriveOpsError as exc:
        flash(str(exc), "error")
    except FileNotFoundError as exc:
        flash(str(exc), "error")
    return redirect(request.form.get("next") or url_for("sources_page"))


@app.route("/drives/<int:drive_id>/scan", methods=["POST"])
def scan_drive(drive_id: int):
    try:
        name, count = scan_catalog_drive(drive_id)
        _sync_library()
        flash(f"Scan complete for “{name}”: {count} media items.", "ok")
    except DriveOpsError as exc:
        flash(str(exc), "error")
    except FileNotFoundError as exc:
        flash(str(exc), "error")
    except Exception as exc:  # noqa: BLE001
        flash(f"Scan failed: {exc}", "error")
    return redirect(request.form.get("next") or url_for("sources_page"))


def _listing_args() -> dict:
    q = request.args.get("q", "").strip()
    kind = request.args.get("kind", "").strip()
    prefix = request.args.get("prefix", "").strip().replace("\\", "/").strip("/")
    try:
        depth = int(request.args.get("depth", "3"))
    except (TypeError, ValueError):
        depth = 3
    depth = max(0, min(depth, 12))
    per_raw = (request.args.get("per") or "500").strip().lower()
    if per_raw in {"all", "0"}:
        per_page = 0
    else:
        try:
            per_page = int(per_raw)
        except (TypeError, ValueError):
            per_page = 500
        if per_page not in {100, 250, 500, 1000}:
            per_page = 500
    page = max(1, request.args.get("page", type=int) or 1)
    return {
        "q": q,
        "kind": kind,
        "prefix": prefix,
        "depth": depth,
        "per_page": per_page,
        "page": page,
    }


def _folded_listing(drive_id: int, args: dict) -> tuple[list, int, int, list[str]]:
    files, file_total = list_media(
        drive_id, q=args["q"] or None, kind=args["kind"] or None
    )
    deepest = max_folder_depth(files)
    depth = min(args["depth"], deepest) if args["depth"] else 0
    rows = fold_by_depth(files, depth, prefix=args["prefix"])
    crumbs = path_parts(args["prefix"])
    return rows, file_total, deepest, crumbs


@app.route("/drives/<int:drive_id>")
def drive_contents(drive_id: int):
    raw = get_drive(drive_id)
    if not raw:
        flash("Drive not found.", "error")
        return redirect(url_for("index"))
    args = _listing_args()
    rows, file_total, deepest, crumbs = _folded_listing(drive_id, args)
    depth = min(args["depth"], deepest) if args["depth"] else 0
    total = len(rows)
    per_page = args["per_page"]
    if per_page == 0:
        pages = 1
        page = 1
        items = rows
        per_page = total or 1
    else:
        pages = max(1, (total + per_page - 1) // per_page)
        page = min(args["page"], pages)
        start = (page - 1) * per_page
        items = rows[start : start + per_page]
    return render_template(
        "drive_contents.html",
        drive=enrich_drive(raw),
        items=items,
        total=total,
        file_total=file_total,
        q=args["q"],
        kind=args["kind"],
        prefix=args["prefix"],
        depth=depth,
        max_depth=deepest,
        crumbs=crumbs,
        page=page,
        pages=pages,
        per_page=args["per_page"],
        listing_q={
            "q": args["q"] or None,
            "kind": args["kind"] or None,
            "prefix": args["prefix"] or None,
            "depth": depth,
            "per": "all" if args["per_page"] == 0 else args["per_page"],
        },
    )


@app.route("/drives/<int:drive_id>/pdf")
def drive_pdf(drive_id: int):
    raw = get_drive(drive_id)
    if not raw:
        flash("Drive not found.", "error")
        return redirect(url_for("index"))
    args = _listing_args()
    rows, _file_total, _deepest, _crumbs = _folded_listing(drive_id, args)
    from mmc.pdf_export import build_drive_pdf

    blob = build_drive_pdf(raw, rows)
    slug = "".join(ch if ch.isalnum() else "-" for ch in (raw.get("name") or "drive")).strip("-")
    return Response(
        blob,
        mimetype="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{slug or "drive"}-media.pdf"'},
    )


@app.route("/import-catalog", methods=["POST"])
def import_catalog():
    try:
        source_id, count = import_entertainment_catalog()
        _clear_compare()
        flash(f"Library refreshed — {count} items (source #{source_id}).", "ok")
    except FileNotFoundError as exc:
        flash(str(exc), "error")
    except Exception as exc:  # noqa: BLE001
        flash(f"Import failed: {exc}", "error")
    return redirect(url_for("index"))


@app.route("/compare", methods=["POST"])
def run_compare():
    try:
        groups = compare_loaded()
        _store_groups(groups)
        extras = sum(max(0, len(g.copies) - 1) for g in groups)
        flash(
            f"Compare complete: {len(groups)} duplicate groups, {extras} extra copies.",
            "ok",
        )
    except Exception as exc:  # noqa: BLE001
        flash(f"Compare failed: {exc}", "error")
    return redirect(url_for("groups_page"))


@app.route("/deep-scan", methods=["POST"])
def deep_scan():
    groups = _groups()
    if not groups:
        groups = compare_loaded()
        _store_groups(groups)
    items = [c.item for g in groups for c in g.copies]
    if not items:
        flash("No duplicate copies to deep-scan.", "error")
        return redirect(url_for("groups_page"))
    try:
        probes = deep_scan_paths(items)
        ok = sum(1 for p in probes.values() if p.ok)
        groups = compare_loaded(probes=probes)
        _store_groups(groups)
        flash(
            f"Deep scan finished: {ok}/{len(probes)} files probed. "
            "ffprobe was installed on the file host if it was missing. Scores updated.",
            "ok",
        )
    except Exception as exc:  # noqa: BLE001
        flash(f"Deep scan failed: {exc}", "error")
    return redirect(url_for("groups_page"))


@app.route("/groups")
def groups_page():
    groups = _groups()
    q = request.args.get("q", "").strip().lower()
    kind = request.args.get("kind", "").strip()
    sort = request.args.get("sort", "gap").strip() or "gap"
    view = request.args.get("view", "simple").strip().lower()
    if view not in {"simple", "advanced"}:
        view = "simple"
    page = max(1, request.args.get("page", type=int) or 1)
    per_page = 50

    filtered = groups
    if kind:
        filtered = [g for g in filtered if g.kind == kind]
    if q:
        filtered = [
            g
            for g in filtered
            if q in g.label.lower()
            or q in g.key.lower()
            or any(
                q in (c.item.get("file_name") or "").lower()
                or q in (c.item.get("drive_name") or "").lower()
                for c in g.copies
            )
        ]
    if sort == "copies":
        filtered = sorted(filtered, key=lambda g: (-len(g.copies), g.label.lower()))
    elif sort == "name":
        filtered = sorted(filtered, key=lambda g: g.label.lower())
    else:
        filtered = sorted(filtered, key=lambda g: (-g.score_gap, -len(g.copies), g.label.lower()))

    total = len(filtered)
    pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, pages)
    start = (page - 1) * per_page
    chunk = filtered[start : start + per_page]
    info = pipeline_stats()
    empty_nocompare = [
        {
            "href": url_for("run_compare"),
            "label": "Find duplicates",
            "method": "post",
            "class": "primary",
            "slow": "Comparing the library…",
            "disabled": not info.get("item_count"),
        },
        {"href": url_for("sources_page"), "label": "Manage drives", "class": "ghost"},
    ]
    return render_template(
        "groups.html",
        groups=chunk,
        total=total,
        page=page,
        pages=pages,
        q=q,
        kind=kind,
        sort=sort,
        view=view,
        compared=bool(_CACHE["groups"]),
        stale=bool(db.get_setting("last_compare_json") and not _CACHE["groups"]),
        empty_nocompare=empty_nocompare,
    )


@app.route("/groups/<path:key>")
def group_detail(key: str):
    key = unquote(key)
    groups = _groups()
    match = next((g for g in groups if g.key == key), None)
    if not match:
        flash("Group not found. Re-run compare.", "error")
        return redirect(url_for("groups_page"))
    return render_template("group_detail.html", group=match)


@app.route("/duplicate/delete", methods=["POST"])
def delete_copy():
    path = (request.form.get("path") or "").strip()
    confirm_path = (request.form.get("confirm_path") or "").strip()
    ack = request.form.get("ack") == "yes"
    group_key = (request.form.get("group_key") or "").strip()
    next_url = request.form.get("next") or url_for("groups_page")
    if not path:
        flash("No file was selected.", "error")
        return redirect(next_url)
    if not ack:
        flash("Deletion cancelled — the warning was not acknowledged.", "error")
        return redirect(next_url)
    if confirm_path.replace("\\", "/") != path.replace("\\", "/"):
        flash("Deletion cancelled — the path did not match the file shown.", "error")
        return redirect(next_url)
    groups = _groups()
    found = find_copy(groups, path)
    if not found:
        flash("That file is not in the current duplicate list. Re-run compare.", "error")
        return redirect(url_for("groups_page"))
    group, copy = found
    if copy.is_winner and request.form.get("confirm_keep") != "yes":
        flash("The KEEP copy was not deleted. Confirm again if you really mean that file.", "error")
        return redirect(url_for("group_detail", key=group.key))
    try:
        where = delete_copy_file(copy)
        forget_copy(path)
        _CACHE["groups"] = drop_copy_from_groups(groups, path)
        flash(
            f"Deleted “{copy.item.get('file_name') or path}” ({where}).",
            "ok",
        )
    except DeleteError as exc:
        flash(str(exc), "error")
        return redirect(url_for("group_detail", key=group.key))
    remaining = next((g for g in _groups() if g.key == group_key), None)
    if remaining:
        return redirect(url_for("group_detail", key=remaining.key))
    return redirect(url_for("groups_page"))


@app.route("/export.json")
def export_json():
    groups = _groups()
    payload = {
        "group_count": len(groups),
        "groups": [
            {
                "key": g.key,
                "label": g.label,
                "kind": g.kind,
                "score_gap": g.score_gap,
                "keep": {
                    "path": g.winner.item.get("file_path") if g.winner else None,
                    "file": g.winner.item.get("file_name") if g.winner else None,
                    "score": g.winner.score.total if g.winner else None,
                    "summary": g.winner.score.summary if g.winner else None,
                },
                "extras": [
                    {
                        "path": c.item.get("file_path"),
                        "file": c.item.get("file_name"),
                        "score": c.score.total,
                        "summary": c.score.summary,
                    }
                    for c in g.extras
                ],
            }
            for g in groups
        ],
    }
    return Response(
        json.dumps(payload, indent=2),
        mimetype="application/json",
        headers={"Content-Disposition": "attachment; filename=duplicate_keepers.json"},
    )


@app.route("/export.csv")
def export_csv():
    groups = _groups()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["title", "kind", "role", "score", "summary", "drive", "path", "size_bytes"]
    )
    for g in groups:
        for c in g.copies:
            writer.writerow(
                [
                    g.label,
                    g.kind,
                    "keep" if c.is_winner else "extra",
                    c.score.total,
                    c.score.summary,
                    c.item.get("drive_name") or "",
                    c.item.get("file_path") or "",
                    c.item.get("size_bytes") or 0,
                ]
            )
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=duplicate_keepers.csv"},
    )


@app.route("/setup")
def setup_page():
    return render_template("setup.html")


@app.route("/api/setup/machine")
def api_setup_machine():
    from mmc.topology import machine_snapshot

    return Response(json.dumps(machine_snapshot()), mimetype="application/json")


@app.route("/api/setup/lan-scan")
def api_setup_lan_scan():
    from mmc.topology import scan_network

    quick = request.args.get("quick", "").strip().lower() in {"1", "true", "yes"}
    return Response(json.dumps(scan_network(quick=quick)), mimetype="application/json")


@app.route("/api/setup/plan", methods=["POST"])
def api_setup_plan():
    from mmc.topology import machine_snapshot, recommend

    body = request.get_json(silent=True) or {}
    plan = recommend(
        role=str(body.get("role") or "catalog"),
        files_where=str(body.get("files_where") or "windows"),
        this=machine_snapshot(),
        peers=list(body.get("peers") or []),
    )
    return Response(json.dumps(plan), mimetype="application/json")


@app.route("/help")
def help_page():
    return render_template("help.html")


def _host_pack_py() -> Path | None:
    here = Path(__file__).resolve().parent
    catalog = find_catalog_db()
    candidates = [
        here / "media-host" / "host-installer" / "pack.py",
        here / "host-installer" / "pack.py",
    ]
    if catalog:
        # catalog.db lives in .../data/; installer is sibling host-installer/
        candidates.insert(0, catalog.parent.parent / "host-installer" / "pack.py")
    for path in candidates:
        if path.is_file():
            return path
    return None


@app.route("/download/media-host-setup.zip")
def download_host_setup():
    """Click-and-run Media Host 1.6 installer (Windows, Linux, or Mac)."""
    pack = _host_pack_py()
    if not pack:
        flash("Host installer pack not found (media-host/host-installer).", "error")
        return redirect(url_for("setup_page"))
    pack_dir = str(pack.parent)
    if pack_dir not in sys.path:
        sys.path.insert(0, pack_dir)
    from pack import build_zip_bytes

    return Response(
        build_zip_bytes(),
        mimetype="application/zip",
        headers={
            "Content-Disposition": "attachment; filename=media-host-setup-1.6.zip"
        },
    )


def main() -> None:
    db.init_db()
    print(f"Media Comparator → http://{HOST}:{PORT}")
    print("Library, free space, and duplicate ranking in one UI.")
    app.run(host=HOST, port=PORT, debug=False)


if __name__ == "__main__":
    main()
