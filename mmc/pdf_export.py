"""Print-ready PDF listing for one catalog volume."""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from mmc.scanner import format_size


def _kind_label(kind: str | None) -> str:
    if kind == "episode":
        return "TV"
    if kind == "audio":
        return "Audio"
    return kind or ""


def _escape(text: Any) -> str:
    return (
        str(text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def build_drive_pdf(
    drive: dict[str, Any],
    items: list[dict[str, Any]],
    page_size=letter,
) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=page_size,
        leftMargin=0.55 * inch,
        rightMargin=0.55 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
        title=f"Media list — {drive.get('name') or 'Drive'}",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TitleCustom",
        parent=styles["Heading1"],
        fontSize=16,
        spaceAfter=4,
        alignment=TA_LEFT,
    )
    meta_style = ParagraphStyle(
        "Meta",
        parent=styles["Normal"],
        fontSize=9,
        textColor=colors.HexColor("#444444"),
        spaceAfter=2,
    )
    cell_style = ParagraphStyle(
        "Cell",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
    )
    header_style = ParagraphStyle(
        "HeaderCell",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
        textColor=colors.white,
        fontName="Helvetica-Bold",
    )

    story: list[Any] = []
    story.append(Paragraph(_escape(drive.get("name") or "Drive"), title_style))
    story.append(Paragraph(f"Path: {_escape(drive.get('root_path') or '')}", meta_style))
    scanned = drive.get("last_scanned_at") or "never"
    story.append(
        Paragraph(
            f"Items: {len(items)} &nbsp;|&nbsp; Last scan: {_escape(str(scanned))}",
            meta_style,
        )
    )
    story.append(
        Paragraph(
            f"Printed: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            meta_style,
        )
    )
    story.append(Spacer(1, 8))

    if not items:
        story.append(Paragraph("No media items found on this volume.", styles["Normal"]))
        doc.build(story)
        return buffer.getvalue()

    header = [
        Paragraph("#", header_style),
        Paragraph("Title", header_style),
        Paragraph("Type", header_style),
        Paragraph("Ext", header_style),
        Paragraph("Size", header_style),
        Paragraph("Path", header_style),
    ]
    data = [header]
    for i, item in enumerate(items, start=1):
        if item.get("is_folder"):
            n = int(item.get("file_count") or 0)
            kind = f"folder · {n} file{'s' if n != 1 else ''}"
            ext = ""
        else:
            kind = _kind_label(item.get("kind"))
            ext = (item.get("extension") or "").lstrip(".")
        data.append(
            [
                Paragraph(str(i), cell_style),
                Paragraph(
                    _escape(item.get("display_title") or item.get("file_name") or ""),
                    cell_style,
                ),
                Paragraph(_escape(kind), cell_style),
                Paragraph(_escape(ext), cell_style),
                Paragraph(format_size(item.get("size_bytes") or 0), cell_style),
                Paragraph(_escape(item.get("relative_path") or ""), cell_style),
            ]
        )

    table = Table(
        data,
        colWidths=[
            0.35 * inch,
            2.5 * inch,
            0.7 * inch,
            0.45 * inch,
            0.7 * inch,
            2.7 * inch,
        ],
        repeatRows=1,
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ALIGN", (0, 0), (0, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [colors.white, colors.HexColor("#f1f5f9")],
                ),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story.append(table)
    doc.build(story)
    return buffer.getvalue()
