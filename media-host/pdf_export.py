"""Generate print-ready PDF lists per drive."""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch, mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from scanner import format_size


def _kind_label(kind: str | None) -> str:
    if kind == "episode":
        return "TV Show"
    if kind == "audio":
        return "MP3/FLAC"
    return kind or ""


def build_drive_pdf(
    drive: dict[str, Any],
    items: list[dict[str, Any]],
    drive_tags: list[str] | None = None,
    page_size=letter,
) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=page_size,
        leftMargin=0.6 * inch,
        rightMargin=0.6 * inch,
        topMargin=0.55 * inch,
        bottomMargin=0.55 * inch,
        title=f"Media list — {drive['name']}",
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
    story.append(Paragraph(_escape(drive["name"]), title_style))
    story.append(
        Paragraph(f"Path: {_escape(drive['root_path'])}", meta_style)
    )
    scanned = drive.get("last_scanned_at") or "never"
    tags_line = ", ".join(drive_tags) if drive_tags else "—"
    story.append(
        Paragraph(
            f"Items: {len(items)} &nbsp;|&nbsp; Last scan: {_escape(str(scanned))} "
            f"&nbsp;|&nbsp; Drive tags: {_escape(tags_line)}",
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
        story.append(Paragraph("No media items found on this drive.", styles["Normal"]))
        doc.build(story)
        return buffer.getvalue()

    header = [
        Paragraph("#", header_style),
        Paragraph("Title", header_style),
        Paragraph("Type", header_style),
        Paragraph("Ext", header_style),
        Paragraph("Size", header_style),
        Paragraph("Tags", header_style),
        Paragraph("Path", header_style),
    ]
    data = [header]

    for i, item in enumerate(items, start=1):
        tags = item.get("tags") or "—"
        data.append(
            [
                Paragraph(str(i), cell_style),
                Paragraph(_escape(item.get("display_title") or item["file_name"]), cell_style),
                Paragraph(_escape(_kind_label(item.get("kind"))), cell_style),
                Paragraph(_escape((item.get("extension") or "").lstrip(".")), cell_style),
                Paragraph(format_size(item.get("size_bytes") or 0), cell_style),
                Paragraph(_escape(str(tags)), cell_style),
                Paragraph(_escape(item.get("relative_path") or ""), cell_style),
            ]
        )

    col_widths = [
        0.35 * inch,
        2.2 * inch,
        0.55 * inch,
        0.4 * inch,
        0.6 * inch,
        1.0 * inch,
        2.3 * inch,
    ]
    table = Table(data, colWidths=col_widths, repeatRows=1)
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


def _escape(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def build_all_media_pdf(
    items: list[dict[str, Any]],
    *,
    title: str = "All media",
    page_size=letter,
) -> bytes:
    """Combined catalog PDF with a Drive column."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=page_size,
        leftMargin=0.5 * inch,
        rightMargin=0.5 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
        title=title,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TitleCustom",
        parent=styles["Heading1"],
        fontSize=16,
        spaceAfter=4,
    )
    meta_style = ParagraphStyle(
        "Meta",
        parent=styles["Normal"],
        fontSize=9,
        textColor=colors.HexColor("#444444"),
        spaceAfter=2,
    )
    cell_style = ParagraphStyle(
        "Cell", parent=styles["Normal"], fontSize=7.5, leading=9.5
    )
    header_style = ParagraphStyle(
        "HeaderCell",
        parent=styles["Normal"],
        fontSize=7.5,
        leading=9.5,
        textColor=colors.white,
        fontName="Helvetica-Bold",
    )

    story: list[Any] = [
        Paragraph(_escape(title), title_style),
        Paragraph(
            f"Items: {len(items)} &nbsp;|&nbsp; "
            f"Printed: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            meta_style,
        ),
        Spacer(1, 8),
    ]

    if not items:
        story.append(Paragraph("No media items in the catalog.", styles["Normal"]))
        doc.build(story)
        return buffer.getvalue()

    header = [
        Paragraph("#", header_style),
        Paragraph("Title", header_style),
        Paragraph("Drive", header_style),
        Paragraph("Type", header_style),
        Paragraph("Ext", header_style),
        Paragraph("Size", header_style),
        Paragraph("Tags", header_style),
        Paragraph("Path", header_style),
    ]
    data = [header]
    for i, item in enumerate(items, start=1):
        data.append(
            [
                Paragraph(str(i), cell_style),
                Paragraph(
                    _escape(item.get("display_title") or item.get("file_name") or ""),
                    cell_style,
                ),
                Paragraph(_escape(item.get("drive_name") or ""), cell_style),
                Paragraph(_escape(_kind_label(item.get("kind"))), cell_style),
                Paragraph(
                    _escape((item.get("extension") or "").lstrip(".")), cell_style
                ),
                Paragraph(format_size(item.get("size_bytes") or 0), cell_style),
                Paragraph(_escape(str(item.get("tags") or "—")), cell_style),
                Paragraph(
                    _escape(item.get("relative_path") or item.get("file_path") or ""),
                    cell_style,
                ),
            ]
        )

    col_widths = [
        0.3 * inch,
        1.9 * inch,
        1.0 * inch,
        0.55 * inch,
        0.35 * inch,
        0.55 * inch,
        0.85 * inch,
        2.0 * inch,
    ]
    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                ("ALIGN", (0, 0), (0, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [colors.white, colors.HexColor("#f1f5f9")],
                ),
                ("LEFTPADDING", (0, 0), (-1, -1), 2),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    story.append(table)
    doc.build(story)
    return buffer.getvalue()
