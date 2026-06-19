"""
pdf_report.py — Generates a polished PDF report from a SiteTestRun's results.
"""

from datetime import datetime
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable, KeepTogether
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER

NAVY    = colors.HexColor("#1e293b")
SLATE   = colors.HexColor("#64748b")
GREEN   = colors.HexColor("#16a34a")
GREEN_BG = colors.HexColor("#f0fdf4")
RED     = colors.HexColor("#dc2626")
RED_BG  = colors.HexColor("#fef2f2")
AMBER   = colors.HexColor("#d97706")
AMBER_BG = colors.HexColor("#fffbeb")
GRAY_BG = colors.HexColor("#f8fafc")
BORDER  = colors.HexColor("#e2e8f0")
ACCENT  = colors.HexColor("#2563eb")


def _verdict_color(verdict: str):
    return {
        "OK": (GREEN, GREEN_BG),
        "PARSE_OK_NO_MATCH": (AMBER, AMBER_BG),
        "FETCH_FAIL": (RED, RED_BG),
        "PARSE_FAIL": (RED, RED_BG),
        "SKIP": (SLATE, GRAY_BG),
    }.get(verdict, (SLATE, GRAY_BG))


def _verdict_label(verdict: str) -> str:
    return {
        "OK": "Working",
        "PARSE_OK_NO_MATCH": "No Match",
        "FETCH_FAIL": "Fetch Failed",
        "PARSE_FAIL": "Parse Failed",
        "SKIP": "Skipped",
    }.get(verdict, verdict)


def generate_pdf_report(run, results: list[dict], summary: dict) -> BytesIO:
    """
    run:      SiteTestRun ORM object (for id, threshold, started_at, etc.)
    results:  list of per-site result dicts
    summary:  dict from test_engine.summarize()
    Returns a BytesIO buffer containing the PDF.
    """
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=18*mm, bottomMargin=16*mm,
        leftMargin=16*mm, rightMargin=16*mm,
        title=f"Site Test Report #{run.id}",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitle", parent=styles["Title"],
        fontSize=20, textColor=NAVY, spaceAfter=2, alignment=TA_LEFT,
    )
    subtitle_style = ParagraphStyle(
        "ReportSubtitle", parent=styles["Normal"],
        fontSize=10, textColor=SLATE, spaceAfter=14,
    )
    h2_style = ParagraphStyle(
        "H2", parent=styles["Heading2"],
        fontSize=13, textColor=NAVY, spaceBefore=16, spaceAfter=8,
    )
    body_style = ParagraphStyle(
        "Body", parent=styles["Normal"], fontSize=9, textColor=NAVY, leading=13,
    )
    small_style = ParagraphStyle(
        "Small", parent=styles["Normal"], fontSize=8, textColor=SLATE, leading=11,
    )
    cell_style = ParagraphStyle(
        "Cell", parent=styles["Normal"], fontSize=8.5, textColor=NAVY, leading=11,
    )
    cell_dim_style = ParagraphStyle(
        "CellDim", parent=styles["Normal"], fontSize=7.5, textColor=SLATE, leading=10,
    )

    story = []

    # ── Header ───────────────────────────────────────────────────────────────
    story.append(Paragraph("Site Test Report", title_style))
    started = run.started_at.strftime("%d %b %Y, %H:%M") if run.started_at else "—"
    completed = run.completed_at.strftime("%d %b %Y, %H:%M") if run.completed_at else "In progress"
    story.append(Paragraph(
        f"Run #{run.id} &nbsp;·&nbsp; Started {started} &nbsp;·&nbsp; "
        f"Completed {completed} &nbsp;·&nbsp; Threshold {run.threshold:.0f}%",
        subtitle_style,
    ))
    story.append(HRFlowable(width="100%", thickness=1, color=BORDER, spaceAfter=14))

    # ── Summary cards (as a table acting like cards) ──────────────────────────
    def stat_cell(label, value, color):
        return Table(
            [[Paragraph(f"<font size=18 color='{color.hexval()}'><b>{value}</b></font>", body_style)],
             [Paragraph(f"<font size=8 color='{SLATE.hexval()}'>{label}</font>", body_style)]],
            colWidths=[34*mm],
        )

    summary_table = Table(
        [[
            stat_cell("Working", summary["ok"], GREEN),
            stat_cell("No Match", summary["parse_ok_no_match"], AMBER),
            stat_cell("Fetch Failed", summary["fetch_fail"], RED),
            stat_cell("Parse Failed", summary["parse_fail"], RED),
            stat_cell("Skipped", summary["skipped"], SLATE),
        ]],
        colWidths=[34*mm]*5,
    )
    summary_table.setStyle(TableStyle([
        ("BOX", (0,0), (-1,-1), 0.75, BORDER),
        ("INNERGRID", (0,0), (-1,-1), 0.75, BORDER),
        ("BACKGROUND", (0,0), (-1,-1), GRAY_BG),
        ("TOPPADDING", (0,0), (-1,-1), 8),
        ("BOTTOMPADDING", (0,0), (-1,-1), 8),
        ("ALIGN", (0,0), (-1,-1), "CENTER"),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        f"{summary['total']} sites tested &nbsp;·&nbsp; total fetch time {summary['total_elapsed']:.1f}s",
        small_style,
    ))

    # ── Results table ──────────────────────────────────────────────────────
    story.append(Paragraph("Results by Site", h2_style))

    header = ["Site", "Domain", "Verdict", "Items", "Matched", "Time", "Product Tested"]
    table_data = [header]

    sorted_results = sorted(results, key=lambda r: (r["verdict"] != "OK", r["domain"]))

    row_colors = []
    for r in sorted_results:
        fg, bg = _verdict_color(r["verdict"])
        verdict_cell = Paragraph(
            f"<font color='{fg.hexval()}'><b>{_verdict_label(r['verdict'])}</b></font>", cell_style
        )
        table_data.append([
            Paragraph(r["name"], cell_style),
            Paragraph(r["domain"], cell_dim_style),
            verdict_cell,
            Paragraph(str(r["items"]), cell_style),
            Paragraph(str(r["matched"]), cell_style),
            Paragraph(f"{r['elapsed']:.1f}s" if r["elapsed"] else "—", cell_dim_style),
            Paragraph(r["product"][:40] + ("…" if len(r["product"]) > 40 else ""), cell_dim_style),
        ])
        row_colors.append(bg)

    col_widths = [32*mm, 38*mm, 24*mm, 14*mm, 16*mm, 14*mm, 40*mm]
    results_table = Table(table_data, colWidths=col_widths, repeatRows=1)

    tstyle = [
        ("BACKGROUND", (0,0), (-1,0), NAVY),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTSIZE", (0,0), (-1,0), 8.5),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("TOPPADDING", (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING", (0,0), (-1,-1), 6),
        ("GRID", (0,0), (-1,-1), 0.5, BORDER),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
    ]
    for i, bg in enumerate(row_colors, start=1):
        tstyle.append(("BACKGROUND", (0,i), (-1,i), bg))
    results_table.setStyle(TableStyle(tstyle))
    story.append(results_table)

    # ── Failure details ──────────────────────────────────────────────────────
    fetch_fail = [r for r in results if r["verdict"] == "FETCH_FAIL"]
    parse_fail = [r for r in results if r["verdict"] == "PARSE_FAIL"]

    if fetch_fail:
        story.append(Paragraph("Fetch Failures — Detail", h2_style))
        ff_data = [["Domain", "HTTP Status", "Error"]]
        for r in sorted(fetch_fail, key=lambda x: x["domain"]):
            ff_data.append([
                Paragraph(r["domain"], cell_style),
                Paragraph(str(r["status"]), cell_style),
                Paragraph((r["error"] or "")[:80], cell_dim_style),
            ])
        ff_table = Table(ff_data, colWidths=[40*mm, 24*mm, 100*mm], repeatRows=1)
        ff_table.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), RED),
            ("TEXTCOLOR", (0,0), (-1,0), colors.white),
            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE", (0,0), (-1,0), 8.5),
            ("GRID", (0,0), (-1,-1), 0.5, BORDER),
            ("BACKGROUND", (0,1), (-1,-1), RED_BG),
            ("TOPPADDING", (0,0), (-1,-1), 5),
            ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ]))
        story.append(ff_table)

    if parse_fail:
        story.append(Paragraph("Parse Failures — Detail", h2_style))
        pf_data = [["Domain", "Items Found", "Note"]]
        for r in sorted(parse_fail, key=lambda x: x["domain"]):
            pf_data.append([
                Paragraph(r["domain"], cell_style),
                Paragraph(str(r["items"]), cell_style),
                Paragraph("Selectors may need updating", cell_dim_style),
            ])
        pf_table = Table(pf_data, colWidths=[40*mm, 30*mm, 94*mm], repeatRows=1)
        pf_table.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), AMBER),
            ("TEXTCOLOR", (0,0), (-1,0), colors.white),
            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE", (0,0), (-1,0), 8.5),
            ("GRID", (0,0), (-1,-1), 0.5, BORDER),
            ("BACKGROUND", (0,1), (-1,-1), AMBER_BG),
            ("TOPPADDING", (0,0), (-1,-1), 5),
            ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ]))
        story.append(pf_table)

    # ── Sample matched products (for OK sites) ───────────────────────────────
    ok_with_samples = [r for r in results if r["verdict"] == "OK" and r.get("sample_items")]
    if ok_with_samples:
        story.append(PageBreak())
        story.append(Paragraph("Sample Matched Products", h2_style))
        story.append(Paragraph(
            "Up to 5 matched listings per working site, for spot-checking accuracy.",
            small_style,
        ))
        story.append(Spacer(1, 6))

        for r in ok_with_samples:
            block = []
            block.append(Paragraph(f"<b>{r['name']}</b> &nbsp;<font color='{SLATE.hexval()}'>({r['domain']})</font>", body_style))
            sample_data = [["Title", "Price"]]
            for item in r["sample_items"]:
                price = item.get("price")
                price_str = f"${price:.2f}" if isinstance(price, (int, float)) else "—"
                sample_data.append([
                    Paragraph((item.get("title") or "")[:90], cell_dim_style),
                    Paragraph(price_str, cell_style),
                ])
            sample_table = Table(sample_data, colWidths=[140*mm, 24*mm], repeatRows=1)
            sample_table.setStyle(TableStyle([
                ("BACKGROUND", (0,0), (-1,0), GRAY_BG),
                ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
                ("FONTSIZE", (0,0), (-1,0), 8),
                ("GRID", (0,0), (-1,-1), 0.4, BORDER),
                ("TOPPADDING", (0,0), (-1,-1), 4),
                ("BOTTOMPADDING", (0,0), (-1,-1), 4),
            ]))
            block.append(Spacer(1, 3))
            block.append(sample_table)
            block.append(Spacer(1, 10))
            story.append(KeepTogether(block))

    # ── Footer note ────────────────────────────────────────────────────────
    story.append(Spacer(1, 16))
    story.append(HRFlowable(width="100%", thickness=0.5, color=BORDER, spaceAfter=6))
    story.append(Paragraph(
        f"Generated {datetime.utcnow().strftime('%d %b %Y, %H:%M UTC')} · Price Monitor Site Test Engine",
        small_style,
    ))

    doc.build(story)
    buf.seek(0)
    return buf
