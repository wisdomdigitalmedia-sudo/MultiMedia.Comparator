"""Media Catalog — local web UI for scanning mounted drives."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

import db
from config import HOST, PORT, SECRET_KEY
from ods_export import build_drive_ods, build_media_ods
from pdf_export import build_all_media_pdf, build_drive_pdf
from remote_client import (
    RemoteAgentError,
    fetch_remote_smart,
    health,
    list_windows_drives,
    scan_remote_path,
)
from scanner import format_size, scan_root
from smart_health import (
    classify_drive_hardware,
    detect_drive_product,
    hardware_label,
    normalize_agent_smart,
    probe_local_smart,
    product_label,
    report_to_storage,
    status_label,
)

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.jinja_env.filters["filesize"] = format_size
app.jinja_env.filters["smart_label"] = status_label
app.jinja_env.filters["hw_label"] = hardware_label
app.jinja_env.filters["product_label"] = product_label

_STATIC_DIR = Path(__file__).resolve().parent / "static"


@app.context_processor
def _inject_asset_versions() -> dict:
    """Cache-bust static CSS/JS when files change on disk."""
    css = _STATIC_DIR / "style.css"
    try:
        css_v = int(css.stat().st_mtime)
    except OSError:
        css_v = 0
    return {"css_v": css_v}


@app.before_request
def _init() -> None:
    db.init_db()


def _is_remote(drive: dict) -> bool:
    return (drive.get("source_type") or "local") == "remote"


def _drive_letter(root_path: str) -> str:
    """Best-effort Windows drive letter from a catalog path (E:/, e, D:\\…)."""
    text = (root_path or "").strip().replace("\\", "/")
    if len(text) >= 1 and text[0].isalpha() and (len(text) == 1 or text[1] in ":/"):
        return text[0].upper()
    return ""


def _enrich_hardware_fields(d: dict) -> dict:
    """Ensure hardware_type / product icon fields are set for UI."""
    hw = (d.get("hardware_type") or "").strip()
    label = (d.get("hardware_label") or "").strip()
    # Always re-classify when unknown, or when we can improve from name/path
    if not hw or hw == "unknown":
        hw, label = classify_drive_hardware(
            media=str(d.get("smart_media") or ""),
            bus=str(d.get("smart_bus") or ""),
            model=str(d.get("smart_model") or ""),
            detail=str(d.get("smart_detail") or ""),
            name=str(d.get("name") or ""),
            root_path=str(d.get("root_path") or ""),
        )
    d["hardware_type"] = hw or "unknown"
    d["hardware_label"] = label or hardware_label(hw)
    d["letter"] = d.get("letter") or _drive_letter(d.get("root_path") or "")

    # Brand / product-line for specific portable icons
    # Volume label (Elements, My Book, …) is the best product cue
    vol = str(d.get("volume_label") or "")
    prod_id, prod_label = detect_drive_product(
        name=str(d.get("name") or ""),
        model=str(d.get("smart_model") or ""),
        volume_label=vol,
        root_path=str(d.get("root_path") or ""),
        media=str(d.get("smart_media") or ""),
        bus=str(d.get("smart_bus") or ""),
        hardware_type=d["hardware_type"],
    )
    d["product_id"] = prod_id
    d["product_label"] = prod_label
    return d


def _catalog_drives_for_ui(agent_url: str = "") -> list[dict]:
    """Existing catalog drives with display helpers for the Add form map."""
    agent_url = (agent_url or "").strip().rstrip("/")
    out: list[dict] = []
    for d in db.list_drives():
        d = dict(d)
        d["is_remote"] = _is_remote(d)
        d["letter"] = _drive_letter(d.get("root_path") or "")
        d["tag_list"] = db.get_drive_tags(d["id"])
        d = _enrich_hardware_fields(d)
        # Match same agent host when comparing
        d_url = (d.get("agent_url") or "").strip().rstrip("/")
        d["same_agent"] = bool(
            agent_url
            and d_url
            and d_url.replace("https://", "http://").lower()
            == agent_url.replace("https://", "http://").lower()
        )
        out.append(d)
    # Remotes on this agent first, then other remotes, then local
    out.sort(
        key=lambda x: (
            0 if x.get("same_agent") else 1 if x.get("is_remote") else 2,
            x.get("letter") or "Z",
            (x.get("name") or "").lower(),
        )
    )
    return out


def _render_drive_form(**kwargs):
    """Always attach existing catalog drives for the graphical map."""
    form = kwargs.get("form") or {}
    agent_url = form.get("agent_url") or ""
    if not agent_url and form.get("agent_host"):
        port = form.get("agent_port") or "8766"
        agent_url = f"http://{form['agent_host']}:{port}"
    kwargs.setdefault("existing_drives", _catalog_drives_for_ui(agent_url))
    return render_template("drive_form.html", **kwargs)


def _probe_capacity(drive: dict) -> dict:
    """
    Fetch total/free bytes for a drive.
    Local: shutil.disk_usage. Remote: agent SMART/capacity fields or /api/drives.
    """
    import shutil
    from scanner import normalize_windows_path_str

    out: dict = {
        "total_bytes": None,
        "free_bytes": None,
        "used_bytes": None,
    }
    if _is_remote(drive):
        path = normalize_windows_path_str(drive.get("root_path") or "")
        letter = path[:1].upper() if path else ""
        # Prefer values from SMART report path
        try:
            raw = fetch_remote_smart(
                drive.get("agent_url") or "",
                path,
                token=drive.get("agent_token") or "",
            )
            if isinstance(raw, dict):
                if raw.get("total_bytes") is not None:
                    out["total_bytes"] = int(raw["total_bytes"])
                if raw.get("free_bytes") is not None:
                    out["free_bytes"] = int(raw["free_bytes"])
                if raw.get("used_bytes") is not None:
                    out["used_bytes"] = int(raw["used_bytes"])
        except Exception:  # noqa: BLE001
            pass
        # Fallback: list agent drives
        if out["total_bytes"] is None and letter:
            try:
                from remote_client import list_windows_drives

                for rd in list_windows_drives(
                    drive.get("agent_url") or "",
                    drive.get("agent_token") or "",
                ):
                    rd_letter = (rd.get("letter") or "")[:1].upper()
                    if rd_letter == letter:
                        if rd.get("total_bytes") is not None:
                            out["total_bytes"] = int(rd["total_bytes"])
                        if rd.get("free_bytes") is not None:
                            out["free_bytes"] = int(rd["free_bytes"])
                        if rd.get("used_bytes") is not None:
                            out["used_bytes"] = int(rd["used_bytes"])
                        break
            except Exception:  # noqa: BLE001
                pass
    else:
        root = drive.get("root_path") or ""
        try:
            usage = shutil.disk_usage(root)
            out["total_bytes"] = usage.total
            out["free_bytes"] = usage.free
            out["used_bytes"] = usage.used
        except OSError:
            pass
    if (
        out["used_bytes"] is None
        and out["total_bytes"] is not None
        and out["free_bytes"] is not None
    ):
        out["used_bytes"] = max(0, out["total_bytes"] - out["free_bytes"])
    return out


def _refresh_drive_smart(drive: dict) -> dict:
    """
    Probe SMART/health for one drive; save + apply SMART:* tag.
    Soft-fails: always returns a report (status may be unknown).
    Also refreshes capacity (size / free space).
    """
    from scanner import normalize_windows_path_str
    from smart_health import empty_report

    report: dict
    if _is_remote(drive):
        path = normalize_windows_path_str(drive.get("root_path") or "")
        try:
            raw = fetch_remote_smart(
                drive.get("agent_url") or "",
                path,
                token=drive.get("agent_token") or "",
            )
            # Batch shape vs single report
            if "drives" in raw and "status" not in raw and "health" not in raw:
                letter = path[:1].upper() if path else ""
                entry = (raw.get("drives") or {}).get(letter) or {}
                report = normalize_agent_smart(entry if entry else raw)
                if not entry:
                    report = empty_report(
                        detail="Agent returned batch SMART with no entry for this letter",
                        source="agent-batch",
                        ok=True,
                    )
                # capacity from batch entry
                if entry.get("total_bytes") is not None:
                    report["total_bytes"] = entry.get("total_bytes")
                if entry.get("free_bytes") is not None:
                    report["free_bytes"] = entry.get("free_bytes")
            else:
                report = normalize_agent_smart(raw)
                if raw.get("total_bytes") is not None:
                    report["total_bytes"] = raw.get("total_bytes")
                if raw.get("free_bytes") is not None:
                    report["free_bytes"] = raw.get("free_bytes")
                if raw.get("used_bytes") is not None:
                    report["used_bytes"] = raw.get("used_bytes")
        except RemoteAgentError as exc:
            msg = str(exc)
            if "404" in msg or "Unknown path" in msg:
                report = empty_report(
                    detail=(
                        "Windows agent is outdated (no /api/smart). "
                        "Copy the latest agent.py to the media host and "
                        "restart run_agent.bat (need version 1.1+)."
                    ),
                    source="agent-outdated",
                    ok=False,
                )
            else:
                report = empty_report(
                    detail=msg[:500],
                    source="agent-error",
                    ok=False,
                )
    else:
        report = probe_local_smart(drive.get("root_path") or "")

    # Fill capacity if SMART path missed it
    if report.get("total_bytes") is None or report.get("free_bytes") is None:
        cap = _probe_capacity(drive)
        for k in ("total_bytes", "free_bytes", "used_bytes"):
            if report.get(k) is None and cap.get(k) is not None:
                report[k] = cap[k]

    fields = report_to_storage(report)
    db.update_drive_smart(drive["id"], fields)
    if fields.get("capacity_total_bytes") is not None:
        db.update_drive_capacity(
            drive["id"],
            fields.get("capacity_total_bytes"),
            fields.get("capacity_free_bytes"),
            fields.get("capacity_used_bytes"),
        )
    tag = db.apply_smart_drive_tag(drive["id"], fields["smart_status"])
    report["tag"] = tag
    report["status"] = fields["smart_status"]
    return report


@app.route("/")
def index():
    drives = db.list_drives()
    for d in drives:
        d["tag_list"] = db.get_drive_tags(d["id"])
        d["is_remote"] = _is_remote(d)
        _enrich_hardware_fields(d)
    tags = db.list_tags()
    total = sum(d.get("item_count") or 0 for d in drives)
    return render_template(
        "index.html",
        drives=drives,
        tags=tags,
        total_items=total,
    )


@app.route("/drives/add", methods=["GET", "POST"])
def add_drive():
    source = request.values.get("source", "local").strip().lower()
    if source not in {"local", "remote"}:
        source = "local"

    # Remembered media-host agent (auto-fill last used address)
    defaults = db.get_default_agent()

    if request.method == "POST":
        form_state = {
            "name": request.form.get("name", "").strip(),
            "root_path": request.form.get("root_path", "").strip(),
            "notes": request.form.get("notes", "").strip(),
            "tags": request.form.get("tags", "").strip(),
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
            "tags": "",
            "agent_url": defaults.get("agent_url") or "",
            "agent_token": defaults.get("agent_token") or "",
            "agent_host": defaults.get("agent_host") or "",
            "agent_port": defaults.get("agent_port") or "8766",
        }

    remote_drives: list[dict] = []
    agent_info: dict | None = None
    list_error: str | None = None

    def _ensure_agent_url() -> None:
        if not form_state["agent_url"] and form_state["agent_host"]:
            form_state["agent_url"] = (
                f"http://{form_state['agent_host']}:{form_state['agent_port']}"
            )

    # Build agent URL from host+port if needed
    if source == "remote":
        _ensure_agent_url()

    action = request.form.get("action", "save") if request.method == "POST" else ""

    if request.method == "POST" and action == "list_remote":
        _ensure_agent_url()
        try:
            agent_info = health(
                form_state["agent_url"], form_state["agent_token"]
            )
            remote_drives = list_windows_drives(
                form_state["agent_url"], form_state["agent_token"]
            )
            # Mark letters already in the catalog (same agent)
            existing = _catalog_drives_for_ui(form_state["agent_url"])
            taken = {
                (d.get("letter") or "").upper()
                for d in existing
                if d.get("same_agent") and d.get("letter")
            }
            # Also match by normalized path
            taken_paths = {
                (d.get("root_path") or "").replace("\\", "/").lower().rstrip("/")
                for d in existing
                if d.get("is_remote")
            }
            for rd in remote_drives:
                letter = (rd.get("letter") or "")[:1].upper()
                path = (rd.get("path") or f"{letter}:/").replace("\\", "/").lower().rstrip("/")
                rd["already_added"] = letter in taken or path in taken_paths
            # Persist host for next time
            db.save_default_agent(
                agent_url=form_state["agent_url"],
                agent_host=form_state["agent_host"],
                agent_port=form_state["agent_port"],
                agent_token=form_state["agent_token"],
            )
            flash(
                f"Connected to {agent_info.get('hostname', 'Windows PC')} — "
                f"{len(remote_drives)} drive(s) found. "
                f"Agent {form_state['agent_url']} saved as default.",
                "ok",
            )
        except RemoteAgentError as exc:
            list_error = str(exc)
            flash(list_error, "error")
        return _render_drive_form(
            drive=None,
            mode="add",
            source=source,
            form=form_state,
            remote_drives=remote_drives,
            agent_info=agent_info,
            tags_value=form_state["tags"],
            agent_default=True,
        )

    if request.method == "POST" and action == "save":
        name = form_state["name"]
        root_path = form_state["root_path"]
        notes = form_state["notes"]
        tags_raw = form_state["tags"]

        if not name or not root_path:
            flash("Name and path are required.", "error")
            return _render_drive_form(
                drive=None,
                mode="add",
                source=source,
                form=form_state,
                remote_drives=remote_drives,
                tags_value=tags_raw,
            )

        try:
            if source == "local":
                path = Path(root_path).expanduser()
                if not path.is_dir():
                    flash(
                        f"Path not found or not a directory "
                        f"(is the share mounted?): {path}",
                        "error",
                    )
                    return _render_drive_form(
                        drive=None,
                        mode="add",
                        source=source,
                        form=form_state,
                        tags_value=tags_raw,
                    )
                drive_id = db.add_drive(name, str(path), notes, source_type="local")
            else:
                if not form_state["agent_url"]:
                    flash("Windows PC address (agent URL or host) is required.", "error")
                    return _render_drive_form(
                        drive=None,
                        mode="add",
                        source=source,
                        form=form_state,
                        tags_value=tags_raw,
                    )
                # Quick reachability check
                health(form_state["agent_url"], form_state["agent_token"])
                from scanner import normalize_windows_path_str

                remote_path = normalize_windows_path_str(root_path)
                drive_id = db.add_drive(
                    name,
                    remote_path,
                    notes,
                    source_type="remote",
                    agent_url=form_state["agent_url"],
                    agent_token=form_state["agent_token"],
                )
                # Remember host so the next drive is pre-filled
                db.save_default_agent(
                    agent_url=form_state["agent_url"],
                    agent_host=form_state["agent_host"],
                    agent_port=form_state["agent_port"],
                    agent_token=form_state["agent_token"],
                )
            if tags_raw:
                db.set_drive_tags(
                    drive_id, [t.strip() for t in tags_raw.split(",")]
                )
            flash(f"Drive “{name}” added — starting media scan…", "ok")
            # Immediately run media scan (GET ?run=1) so user doesn't need a second click
            return redirect(url_for("scan_drive", drive_id=drive_id, run=1))
        except RemoteAgentError as exc:
            flash(str(exc), "error")
        except Exception as exc:  # noqa: BLE001
            flash(f"Could not add drive: {exc}", "error")

    return _render_drive_form(
        drive=None,
        mode="add",
        source=source,
        form=form_state,
        remote_drives=remote_drives,
        agent_info=agent_info,
        tags_value=form_state.get("tags", ""),
    )


@app.route("/drives/<int:drive_id>")
def drive_detail(drive_id: int):
    drive = db.get_drive(drive_id)
    if not drive:
        flash("Drive not found.", "error")
        return redirect(url_for("index"))
    drive = _enrich_hardware_fields(dict(drive))
    q = request.args.get("q", "").strip() or None
    kind = request.args.get("kind", "").strip() or None
    tag = request.args.get("tag", "").strip() or None
    items = db.list_media(drive_id=drive_id, q=q, kind=kind, tag=tag)
    drive_tags = db.get_drive_tags(drive_id)
    all_tags = db.list_tags()
    return render_template(
        "drive_detail.html",
        drive=drive,
        items=items,
        drive_tags=drive_tags,
        all_tags=all_tags,
        q=q or "",
        kind=kind or "",
        tag=tag or "",
        is_remote=_is_remote(drive),
    )


@app.route("/drives/<int:drive_id>/edit", methods=["GET", "POST"])
def edit_drive(drive_id: int):
    drive = db.get_drive(drive_id)
    if not drive:
        flash("Drive not found.", "error")
        return redirect(url_for("index"))

    source = drive.get("source_type") or "local"
    form_state = {
        "name": drive["name"],
        "root_path": drive["root_path"],
        "notes": drive.get("notes") or "",
        "agent_url": drive.get("agent_url") or "",
        "agent_token": drive.get("agent_token") or "",
        "agent_host": "",
        "agent_port": "8766",
    }
    # Split agent URL for host fields when possible
    url = form_state["agent_url"]
    if url.startswith("http://"):
        rest = url[len("http://") :]
        if ":" in rest:
            host, port = rest.rsplit(":", 1)
            form_state["agent_host"] = host
            form_state["agent_port"] = port
        else:
            form_state["agent_host"] = rest

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        root_path = request.form.get("root_path", "").strip()
        notes = request.form.get("notes", "").strip()
        tags_raw = request.form.get("tags", "").strip()
        agent_url = request.form.get("agent_url", "").strip()
        agent_token = request.form.get("agent_token", "").strip()
        agent_host = request.form.get("agent_host", "").strip()
        agent_port = request.form.get("agent_port", "8766").strip() or "8766"
        if not agent_url and agent_host:
            agent_url = f"http://{agent_host}:{agent_port}"

        form_state.update(
            {
                "name": name,
                "root_path": root_path,
                "notes": notes,
                "agent_url": agent_url,
                "agent_token": agent_token,
                "agent_host": agent_host,
                "agent_port": agent_port,
            }
        )

        if not name or not root_path:
            flash("Name and path are required.", "error")
        else:
            try:
                db.update_drive(
                    drive_id,
                    name,
                    root_path,
                    notes,
                    source_type=source,
                    agent_url=agent_url if source == "remote" else "",
                    agent_token=agent_token if source == "remote" else "",
                )
                db.set_drive_tags(
                    drive_id,
                    [t.strip() for t in tags_raw.split(",")] if tags_raw else [],
                )
                flash("Drive updated.", "ok")
                return redirect(url_for("drive_detail", drive_id=drive_id))
            except Exception as exc:  # noqa: BLE001
                flash(f"Update failed: {exc}", "error")

    tags = ", ".join(db.get_drive_tags(drive_id))
    return _render_drive_form(
        drive=drive,
        mode="edit",
        source=source,
        form=form_state,
        tags_value=tags,
        remote_drives=[],
    )


@app.route("/drives/<int:drive_id>/delete", methods=["POST"])
def delete_drive(drive_id: int):
    drive = db.get_drive(drive_id)
    if drive:
        db.delete_drive(drive_id)
        flash(f"Removed drive “{drive['name']}”.", "ok")
    return redirect(url_for("index"))


def _scan_one_drive(drive: dict) -> tuple[int, str | None]:
    """
    Scan one drive's media. Returns (item_count, error_message_or_None).
    Also refreshes capacity (size / free space) when possible.
    """
    root = drive["root_path"]
    if _is_remote(drive):
        from scanner import normalize_windows_path_str

        root = normalize_windows_path_str(root)
        if root != drive["root_path"]:
            db.update_drive(
                drive["id"],
                drive["name"],
                root,
                drive.get("notes") or "",
                source_type="remote",
                agent_url=drive.get("agent_url") or "",
                agent_token=drive.get("agent_token") or "",
            )
        found = scan_remote_path(
            drive.get("agent_url") or "",
            root,
            token=drive.get("agent_token") or "",
        )
    else:
        found = scan_root(root)
    count = db.upsert_media_items(drive["id"], found)
    # Best-effort capacity update (does not fail the media scan)
    try:
        cap = _probe_capacity(drive if not _is_remote(drive) else {**drive, "root_path": root})
        if cap.get("total_bytes") is not None or cap.get("free_bytes") is not None:
            db.update_drive_capacity(
                drive["id"],
                cap.get("total_bytes"),
                cap.get("free_bytes"),
                cap.get("used_bytes"),
            )
    except Exception:  # noqa: BLE001
        pass
    return count, None


@app.route("/drives/<int:drive_id>/scan", methods=["POST", "GET"])
def scan_drive(drive_id: int):
    """
    Media inventory scan only.

    SMART is intentionally separate (Check SMART button). Bundling CrystalDiskInfo
    into Scan made the first request hang so long it looked like nothing happened.
    GET is allowed only with ?run=1 for the post-add autoscan redirect.
    """
    drive = db.get_drive(drive_id)
    if not drive:
        flash("Drive not found.", "error")
        return redirect(url_for("index"))

    # Autoscan link from "add drive" uses GET ?run=1 once
    if request.method == "GET" and request.args.get("run") != "1":
        return redirect(url_for("drive_detail", drive_id=drive_id))

    try:
        count, _ = _scan_one_drive(drive)
        flash(
            f"Scan complete: {count} media items. "
            f"(Use Check SMART separately for disk health.)",
            "ok",
        )
    except FileNotFoundError as exc:
        flash(str(exc), "error")
    except PermissionError:
        flash("Permission denied reading that path.", "error")
    except RemoteAgentError as exc:
        flash(str(exc), "error")
    except Exception as exc:  # noqa: BLE001
        flash(f"Scan failed: {exc}", "error")

    next_url = request.form.get("next") or url_for("drive_detail", drive_id=drive_id)
    return redirect(next_url)


@app.route("/drives/scan-all", methods=["POST"])
def scan_all_drives():
    """Scan every catalogued drive for media (no SMART)."""
    drives = db.list_drives()
    if not drives:
        flash("No drives to scan.", "error")
        return redirect(url_for("index"))

    ok = 0
    failed = 0
    total_items = 0
    errors: list[str] = []
    for drive in drives:
        try:
            count, _ = _scan_one_drive(drive)
            ok += 1
            total_items += count
        except Exception as exc:  # noqa: BLE001
            failed += 1
            errors.append(f"{drive.get('name')}: {exc}")

    msg = (
        f"Scan all complete: {ok} drive(s) OK, {total_items} media items total"
        + (f", {failed} failed" if failed else "")
        + "."
    )
    flash(msg, "ok" if ok else "error")
    for err in errors[:5]:
        flash(err, "error")
    if len(errors) > 5:
        flash(f"…and {len(errors) - 5} more errors.", "error")
    return redirect(url_for("index"))


@app.route("/drives/<int:drive_id>/smart", methods=["POST"])
def refresh_smart(drive_id: int):
    drive = db.get_drive(drive_id)
    if not drive:
        flash("Drive not found.", "error")
        return redirect(url_for("index"))
    report = _refresh_drive_smart(drive)
    label = status_label(report.get("status", "unknown"))
    temp = report.get("temperature_c")
    extra = f", {temp}°C" if temp is not None else ""
    model = report.get("model") or ""
    detail = (report.get("detail") or "")[:160]
    if report.get("status") == "unknown" and detail:
        flash(
            f"S.M.A.R.T. {label}{extra}"
            + (f" · {model}" if model else "")
            + f" — {detail}",
            "ok",
        )
    else:
        flash(
            f"S.M.A.R.T. {label}{extra}"
            + (f" · {model}" if model else "")
            + f" · tagged {report.get('tag')}",
            "ok",
        )
    next_url = request.form.get("next") or url_for("drive_detail", drive_id=drive_id)
    return redirect(next_url)


@app.route("/drives/smart-all", methods=["POST"])
def refresh_smart_all():
    drives = db.list_drives()
    healthy = warning = failing = unknown = 0
    for drive in drives:
        report = _refresh_drive_smart(drive)
        st = report.get("status") or "unknown"
        if st == "healthy":
            healthy += 1
        elif st == "warning":
            warning += 1
        elif st == "failing":
            failing += 1
        else:
            unknown += 1
    flash(
        f"S.M.A.R.T. refresh done — "
        f"Healthy {healthy}, Warning {warning}, Failing {failing}, Unknown {unknown}. "
        f"Unknown is normal for NAS mappings / some USB docks. "
        f"If everything is Unknown on Windows drives, update & restart the agent.",
        "ok",
    )
    return redirect(url_for("index"))


@app.route("/api/remote/drives", methods=["POST"])
def api_remote_drives():
    """JSON helper: list drives from a Windows agent."""
    data = request.get_json(silent=True) or {}
    agent_url = (data.get("agent_url") or request.form.get("agent_url") or "").strip()
    token = (data.get("agent_token") or request.form.get("agent_token") or "").strip()
    host = (data.get("agent_host") or "").strip()
    port = (data.get("agent_port") or "8766").strip() or "8766"
    if not agent_url and host:
        agent_url = f"http://{host}:{port}"
    if not agent_url:
        return jsonify({"error": "agent_url or agent_host required"}), 400
    try:
        info = health(agent_url, token)
        drives = list_windows_drives(agent_url, token)
        return jsonify({"ok": True, "agent": info, "drives": drives, "agent_url": agent_url})
    except RemoteAgentError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 502


def _safe_filename(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in (name or "export"))


@app.route("/drives/<int:drive_id>/pdf")
def export_pdf(drive_id: int):
    drive = db.get_drive(drive_id)
    if not drive:
        flash("Drive not found.", "error")
        return redirect(url_for("index"))
    items = db.list_media(drive_id=drive_id)
    tags = db.get_drive_tags(drive_id)
    pdf_bytes = build_drive_pdf(drive, items, tags)
    safe = _safe_filename(drive["name"])
    return send_file(
        BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"{safe}_media_list.pdf",
    )


@app.route("/drives/<int:drive_id>/ods")
def export_ods(drive_id: int):
    drive = db.get_drive(drive_id)
    if not drive:
        flash("Drive not found.", "error")
        return redirect(url_for("index"))
    q = request.args.get("q", "").strip() or None
    kind = request.args.get("kind", "").strip() or None
    tag = request.args.get("tag", "").strip() or None
    items = db.list_media(drive_id=drive_id, q=q, kind=kind, tag=tag)
    tags = db.get_drive_tags(drive_id)
    ods_bytes = build_drive_ods(drive, items, tags)
    safe = _safe_filename(drive["name"])
    return send_file(
        BytesIO(ods_bytes),
        mimetype="application/vnd.oasis.opendocument.spreadsheet",
        as_attachment=True,
        download_name=f"{safe}_media_list.ods",
    )


@app.route("/media/ods")
def export_all_ods():
    q = request.args.get("q", "").strip() or None
    kind = request.args.get("kind", "").strip() or None
    tag = request.args.get("tag", "").strip() or None
    drive_id = request.args.get("drive_id", type=int)
    items = db.list_media(drive_id=drive_id, q=q, kind=kind, tag=tag)
    ods_bytes = build_media_ods(
        title="All media",
        items=items,
        include_drive_column=True,
    )
    return send_file(
        BytesIO(ods_bytes),
        mimetype="application/vnd.oasis.opendocument.spreadsheet",
        as_attachment=True,
        download_name="all_media_list.ods",
    )


@app.route("/media/pdf")
def export_all_pdf():
    q = request.args.get("q", "").strip() or None
    kind = request.args.get("kind", "").strip() or None
    tag = request.args.get("tag", "").strip() or None
    drive_id = request.args.get("drive_id", type=int)
    items = db.list_media(drive_id=drive_id, q=q, kind=kind, tag=tag)
    pdf_bytes = build_all_media_pdf(items, title="All media")
    return send_file(
        BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name="all_media_list.pdf",
    )


@app.route("/media")
def all_media():
    q = request.args.get("q", "").strip() or None
    kind = request.args.get("kind", "").strip() or None
    tag = request.args.get("tag", "").strip() or None
    drive_id = request.args.get("drive_id", type=int)
    items = db.list_media(drive_id=drive_id, q=q, kind=kind, tag=tag)
    drives = db.list_drives()
    tags = db.list_tags()
    return render_template(
        "media_list.html",
        items=items,
        drives=drives,
        all_tags=tags,
        q=q or "",
        kind=kind or "",
        tag=tag or "",
        drive_id=drive_id,
    )


@app.route("/media/<int:media_id>", methods=["GET", "POST"])
def media_detail(media_id: int):
    item = db.get_media(media_id)
    if not item:
        flash("Item not found.", "error")
        return redirect(url_for("all_media"))
    if request.method == "POST":
        tags_raw = request.form.get("tags", "")
        db.set_media_tags(
            media_id, [t.strip() for t in tags_raw.split(",") if t.strip()]
        )
        flash("Tags saved.", "ok")
        return redirect(url_for("media_detail", media_id=media_id))
    tags = db.get_media_tags(media_id)
    all_tags = db.list_tags()
    return render_template(
        "media_detail.html",
        item=item,
        tags=tags,
        all_tags=all_tags,
        tags_value=", ".join(tags),
    )


# Last duplicate compare (30–40s on a 100k catalog — do not recompute every GET)
_DUP_CACHE: dict = {"result": None, "kind": "", "error": ""}


@app.route("/duplicates")
def duplicates_page():
    import mmc_bridge

    kind = request.args.get("kind", "").strip() or None
    q = request.args.get("q", "").strip().lower()
    sort = request.args.get("sort", "gap").strip() or "gap"
    page = max(1, request.args.get("page", type=int) or 1)
    available = mmc_bridge.comparator_available()
    result = _DUP_CACHE.get("result")
    groups = []
    extra = 0
    if result and available:
        groups = list(result.groups)
        if kind:
            groups = [g for g in groups if g.kind == kind]
        if q:
            groups = [
                g
                for g in groups
                if q in g.label.lower()
                or any(q in (c.item.get("file_name") or "").lower() for c in g.copies)
            ]
        if sort == "copies":
            groups.sort(key=lambda g: (-len(g.copies), g.label.lower()))
        elif sort == "name":
            groups.sort(key=lambda g: g.label.lower())
        else:
            groups.sort(key=lambda g: (-g.score_gap, -len(g.copies), g.label.lower()))
        extra = result.extra_copies
    per_page = 40
    total = len(groups)
    pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, pages)
    chunk = groups[(page - 1) * per_page : page * per_page]
    return render_template(
        "duplicates.html",
        available=available,
        compared=result is not None,
        groups=chunk,
        total=total,
        extra_copies=extra,
        item_count=(result.item_count if result else 0),
        group_count=(result.group_count if result else 0),
        q=q or "",
        kind=kind or "",
        sort=sort,
        page=page,
        pages=pages,
        error=_DUP_CACHE.get("error") or "",
    )


@app.route("/duplicates/compare", methods=["POST"])
def duplicates_compare():
    import mmc_bridge
    from config import DATABASE_PATH

    kind = request.form.get("kind", "").strip() or None
    try:
        result = mmc_bridge.compare_this_catalog(DATABASE_PATH, kind=None)
        _DUP_CACHE["result"] = result
        _DUP_CACHE["kind"] = kind or ""
        _DUP_CACHE["error"] = ""
        flash(
            f"Compared {result.item_count} catalog items → "
            f"{result.group_count} duplicate groups, {result.extra_copies} extras.",
            "ok",
        )
    except Exception as exc:  # noqa: BLE001
        _DUP_CACHE["error"] = str(exc)
        flash(f"Compare failed: {exc}", "error")
    return redirect(url_for("duplicates_page", kind=kind or None))


@app.route("/duplicates/group")
def duplicates_group():
    from urllib.parse import unquote

    import mmc_bridge

    key = unquote(request.args.get("key") or "")
    result = _DUP_CACHE.get("result")
    if not result or not key:
        flash("Run a compare first.", "error")
        return redirect(url_for("duplicates_page"))
    group = mmc_bridge.group_by_key(result, key)
    if not group:
        flash("Group not found. Re-run compare.", "error")
        return redirect(url_for("duplicates_page"))
    return render_template("duplicate_group.html", group=group)


@app.route("/help")
def help_page():
    return render_template("help.html")


@app.route("/download/agent.py")
def download_agent():
    """Serve the agent file for easy copy to the file host."""
    return send_file(
        Path(__file__).resolve().parent / "agent.py",
        mimetype="text/x-python",
        as_attachment=True,
        download_name="agent.py",
    )


@app.route("/download/agent-pack.zip")
@app.route("/download/media-host-setup.zip")
def download_agent_pack():
    """Click-and-run Media Host 1.6 installer (Windows, Linux, or Mac)."""
    import sys as _sys

    pack_dir = Path(__file__).resolve().parent / "host-installer"
    if str(pack_dir) not in _sys.path:
        _sys.path.insert(0, str(pack_dir))
    from pack import build_zip_bytes

    return send_file(
        BytesIO(build_zip_bytes()),
        mimetype="application/zip",
        as_attachment=True,
        download_name="media-host-setup-1.6.zip",
    )


def main() -> None:
    db.init_db()
    print(f"Media Catalog → http://{HOST}:{PORT}")
    print("Local mounts or media-host agent (agent.py on the file host).")
    app.run(host=HOST, port=PORT, debug=False)


if __name__ == "__main__":
    main()
