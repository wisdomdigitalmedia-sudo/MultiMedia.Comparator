"""Export media lists as OpenDocument Spreadsheet (.ods) files."""

from __future__ import annotations

import re
import zipfile
from datetime import datetime
from io import BytesIO
from typing import Any
from xml.sax.saxutils import escape

from scanner import format_size

# OpenDocument namespace prefixes used in content.xml
_NS = {
    "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
    "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
    "style": "urn:oasis:names:tc:opendocument:xmlns:style:1.0",
    "fo": "urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0",
    "meta": "urn:oasis:names:tc:opendocument:xmlns:meta:1.0",
    "dc": "http://purl.org/dc/elements/1.1/",
    "manifest": "urn:oasis:names:tc:opendocument:xmlns:manifest:1.0",
}


def _kind_label(kind: str | None) -> str:
    if kind == "episode":
        return "TV Show"
    if kind == "audio":
        return "MP3/FLAC"
    return kind or ""


def _cell(value: Any) -> str:
    text = "" if value is None else str(value)
    return (
        f'<table:table-cell office:value-type="string">'
        f"<text:p>{escape(text)}</text:p></table:table-cell>"
    )


def _size_cell(size_bytes: Any) -> str:
    try:
        n = int(size_bytes or 0)
    except (TypeError, ValueError):
        n = 0
    # Store both raw bytes (for sorting in Calc) and human text
    return (
        f'<table:table-cell office:value-type="float" office:value="{n}">'
        f"<text:p>{escape(format_size(n))}</text:p></table:table-cell>"
    )


def _row(cells: list[str]) -> str:
    return "<table:table-row>" + "".join(cells) + "</table:table-row>"


def _sheet_name(name: str) -> str:
    # ODF sheet names: max 31-ish chars; avoid []:*?/\\
    cleaned = re.sub(r"[\[\]:*?/\\]", "_", name or "Sheet")
    cleaned = cleaned.strip() or "Sheet"
    return cleaned[:31]


def build_media_ods(
    title: str,
    items: list[dict[str, Any]],
    *,
    drive: dict[str, Any] | None = None,
    drive_tags: list[str] | None = None,
    include_drive_column: bool = False,
) -> bytes:
    """
    Build a .ods workbook with:
      - Summary sheet (meta)
      - Media sheet (rows)
    """
    sheet = _sheet_name(title)
    generated = datetime.now().strftime("%Y-%m-%d %H:%M")

    headers = ["#", "Title", "Type", "Ext", "Size", "Tags", "Show", "Season", "Episode", "Path"]
    if include_drive_column:
        headers.insert(2, "Drive")

    header_row = _row([_cell(h) for h in headers])
    body_rows: list[str] = []
    for i, item in enumerate(items, start=1):
        cells = [
            _cell(i),
            _cell(item.get("display_title") or item.get("file_name") or ""),
        ]
        if include_drive_column:
            cells.append(_cell(item.get("drive_name") or ""))
        cells.extend(
            [
                _cell(_kind_label(item.get("kind"))),
                _cell((item.get("extension") or "").lstrip(".")),
                _size_cell(item.get("size_bytes")),
                _cell(item.get("tags") or ""),
                _cell(item.get("show_name") or ""),
                _cell(item.get("season") if item.get("season") is not None else ""),
                _cell(item.get("episode") if item.get("episode") is not None else ""),
                _cell(item.get("relative_path") or item.get("file_path") or ""),
            ]
        )
        body_rows.append(_row(cells))

    media_table = (
        f'<table:table table:name="{escape(sheet)}">'
        f'<table:table-column table:number-columns-repeated="{len(headers)}"/>'
        f"{header_row}{''.join(body_rows)}"
        f"</table:table>"
    )

    # Summary sheet
    summary_pairs = [
        ("Title", title),
        ("Generated", generated),
        ("Item count", str(len(items))),
    ]
    if drive:
        summary_pairs.extend(
            [
                ("Drive name", drive.get("name") or ""),
                ("Path", drive.get("root_path") or ""),
                ("Source", drive.get("source_type") or "local"),
                ("Agent", drive.get("agent_url") or ""),
                ("Drive tags", ", ".join(drive_tags or [])),
                ("Last media scan", drive.get("last_scanned_at") or ""),
                ("SMART status", drive.get("smart_status") or ""),
                ("SMART model", drive.get("smart_model") or ""),
                ("SMART checked", drive.get("smart_checked_at") or ""),
            ]
        )
    summary_rows = [
        _row([_cell("Field"), _cell("Value")]),
        *[_row([_cell(k), _cell(v)]) for k, v in summary_pairs],
    ]
    summary_table = (
        '<table:table table:name="Summary">'
        '<table:table-column table:number-columns-repeated="2"/>'
        f"{''.join(summary_rows)}"
        "</table:table>"
    )

    content_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<office:document-content
  xmlns:office="{_NS['office']}"
  xmlns:table="{_NS['table']}"
  xmlns:text="{_NS['text']}"
  xmlns:style="{_NS['style']}"
  xmlns:fo="{_NS['fo']}"
  office:version="1.2">
  <office:automatic-styles>
    <style:style style:name="co1" style:family="table-column">
      <style:table-column-properties style:column-width="2.5cm"/>
    </style:style>
  </office:automatic-styles>
  <office:body>
    <office:spreadsheet>
      {summary_table}
      {media_table}
    </office:spreadsheet>
  </office:body>
</office:document-content>
"""

    styles_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<office:document-styles
  xmlns:office="{_NS['office']}"
  xmlns:style="{_NS['style']}"
  office:version="1.2">
  <office:styles/>
</office:document-styles>
"""

    meta_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<office:document-meta
  xmlns:office="{_NS['office']}"
  xmlns:meta="{_NS['meta']}"
  xmlns:dc="{_NS['dc']}"
  office:version="1.2">
  <office:meta>
    <dc:title>{escape(title)}</dc:title>
    <meta:generator>Media Catalog</meta:generator>
    <meta:creation-date>{datetime.now().isoformat(timespec='seconds')}</meta:creation-date>
  </office:meta>
</office:document-meta>
"""

    manifest_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<manifest:manifest xmlns:manifest="{_NS['manifest']}" manifest:version="1.2">
  <manifest:file-entry manifest:full-path="/" manifest:version="1.2"
    manifest:media-type="application/vnd.oasis.opendocument.spreadsheet"/>
  <manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/>
  <manifest:file-entry manifest:full-path="styles.xml" manifest:media-type="text/xml"/>
  <manifest:file-entry manifest:full-path="meta.xml" manifest:media-type="text/xml"/>
</manifest:manifest>
"""

    buf = BytesIO()
    # mimetype must be first and stored (not deflated) per ODF spec
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "mimetype",
            "application/vnd.oasis.opendocument.spreadsheet",
            compress_type=zipfile.ZIP_STORED,
        )
        zf.writestr("META-INF/manifest.xml", manifest_xml, compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("content.xml", content_xml, compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("styles.xml", styles_xml, compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("meta.xml", meta_xml, compress_type=zipfile.ZIP_DEFLATED)
    return buf.getvalue()


def build_drive_ods(
    drive: dict[str, Any],
    items: list[dict[str, Any]],
    drive_tags: list[str] | None = None,
) -> bytes:
    return build_media_ods(
        title=drive.get("name") or "Drive",
        items=items,
        drive=drive,
        drive_tags=drive_tags,
        include_drive_column=False,
    )
