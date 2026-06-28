"""
services/exporters/pdf_exporter.py — KT Assurance Report PDF export
(Phase 10 / Session 32).

Renders schemas.assurance_report.AssuranceReport (already-aggregated
facts -- see services/assurance_report_service.py) to a paginated PDF
using reportlab's platypus layer (per the pdf skill's "Create PDFs ->
reportlab" guidance). This module only formats already-computed values;
it performs no scoring and adds no new numbers.

Library choice: the pptx skill's pptxgenjs guidance is for interactively
authored, visually designed decks -- this is a backend export of
structured report data with no design requirement, so reportlab (a
Python library callable directly from this service layer) is the
appropriate tool here, same reconciliation the PPTX exporter makes for
python-pptx below.
"""

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from schemas.assurance_report import AssuranceReport

_TABLE_STYLE = TableStyle(
    [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E2761")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CADCFC")),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F7FC")]),
    ]
)


def export_assurance_report_pdf(report: AssuranceReport, output_path: str) -> str:
    doc = SimpleDocTemplate(output_path, pagesize=letter, title=f"KT Assurance Report - {report.program_name}")
    styles = getSampleStyleSheet()
    story = []

    # 1. Cover
    story.append(Paragraph("KT Assurance Report", styles["Title"]))
    story.append(Paragraph(report.program_name, styles["Heading2"]))
    story.append(Spacer(1, 6))
    story.append(Paragraph(f"Report ID: {report.report_id}", styles["Normal"]))
    story.append(Paragraph(f"Generated: {report.generated_at.isoformat()}", styles["Normal"]))
    story.append(Paragraph(f"Program ID: {report.program_id}", styles["Normal"]))
    story.append(PageBreak())

    # 2. Executive summary
    story.append(Paragraph("Executive Summary", styles["Heading1"]))
    health = report.program_health
    summary_rows = [
        ["Metric", "Value"],
        ["Lifecycle State", health.lifecycle_state],
        ["Completion Status", health.completion_status],
        ["Readiness", health.readiness or "Not Assessed"],
        ["At Risk", "Yes" if health.at_risk else "No"],
        ["Average Coverage", f"{health.coverage:.0%}" if health.coverage is not None else "N/A"],
        ["Average OIS", f"{health.ois:.1f}" if health.ois is not None else "N/A"],
        ["Overall Decision", report.overall_decision or "Not Assessed"],
    ]
    story.append(Table(summary_rows, style=_TABLE_STYLE, hAlign="LEFT"))
    story.append(Spacer(1, 18))

    # 3. Coverage assessment
    story.append(Paragraph("Coverage Assessment", styles["Heading1"]))
    if report.coverage_by_package:
        rows = [["Package ID", "Coverage", "Sufficient"]]
        for cov in report.coverage_by_package:
            rows.append([cov.package_id, f"{cov.coverage:.0%}", "Yes" if cov.sufficient else "No"])
        story.append(Table(rows, style=_TABLE_STYLE, hAlign="LEFT"))
    else:
        story.append(Paragraph("No packages have a coverage assessment yet.", styles["Normal"]))
    story.append(Spacer(1, 18))

    # 4. Gap & risk analysis
    story.append(Paragraph("Gap & Risk Analysis", styles["Heading1"]))
    gs = report.gap_summary
    story.append(
        Table(
            [
                ["Total", "Open", "Closed", "Critical", "High Risk"],
                [gs.total, gs.open, gs.closed, gs.critical, gs.high_risk],
            ],
            style=_TABLE_STYLE,
            hAlign="LEFT",
        )
    )
    story.append(Spacer(1, 12))
    risk_rows = [["Domain", "Open Gaps", "Critical Gaps"]]
    for cell in report.risk_concentration:
        risk_rows.append([cell.domain, cell.open_gaps, cell.critical_gaps])
    story.append(Table(risk_rows, style=_TABLE_STYLE, hAlign="LEFT"))
    story.append(Spacer(1, 18))

    # 5. Receiver readiness summary
    story.append(Paragraph("Receiver Readiness Summary", styles["Heading1"]))
    if report.readiness_by_receiver:
        rows = [["Receiver", "OIS", "Status", "Certification"]]
        for rd in report.readiness_by_receiver:
            rows.append([rd.receiver_name, f"{rd.ois:.1f}", rd.readiness_status, rd.certification or "None"])
        story.append(Table(rows, style=_TABLE_STYLE, hAlign="LEFT"))
    else:
        story.append(Paragraph("No receivers have been assessed yet.", styles["Normal"]))
    story.append(Spacer(1, 18))

    # 6. Competency assessment detail
    story.append(Paragraph("Competency Assessment Detail", styles["Heading1"]))
    cs = report.competency_summary
    story.append(
        Table(
            [["Total", "Pass", "Fail", "Warning"], [cs.total, cs.passed, cs.failed, cs.warning]],
            style=_TABLE_STYLE,
            hAlign="LEFT",
        )
    )
    story.append(Spacer(1, 18))

    # 7. Certification & sign-off status
    story.append(Paragraph("Certification & Sign-off Status", styles["Heading1"]))
    if report.certifications:
        rows = [["Receiver", "Readiness", "Certification"]]
        for cert in report.certifications:
            rows.append([cert.receiver_name, cert.readiness_status, cert.certification or "None"])
        story.append(Table(rows, style=_TABLE_STYLE, hAlign="LEFT"))
    else:
        story.append(Paragraph("No certifications issued yet.", styles["Normal"]))
    story.append(Spacer(1, 18))

    # 8. Recommendations
    story.append(Paragraph("Recommendations", styles["Heading1"]))
    if report.recommendations_by_receiver:
        receiver_names = {rd.receiver_id: rd.receiver_name for rd in report.readiness_by_receiver}
        for receiver_id, items in report.recommendations_by_receiver.items():
            if not items:
                continue
            story.append(Paragraph(receiver_names.get(receiver_id, receiver_id), styles["Heading3"]))
            for item in items:
                story.append(
                    Paragraph(
                        f"<b>{item.competency_name}</b> (score {item.score:.0f}): "
                        + "; ".join(item.actions),
                        styles["Normal"],
                    )
                )
    else:
        story.append(Paragraph("No outstanding remediation recommendations.", styles["Normal"]))
    story.append(Spacer(1, 18))

    # 9. Traceability appendix
    story.append(Paragraph("Traceability Appendix", styles["Heading1"]))
    if report.traced_receiver_readiness_ids:
        story.append(
            Paragraph(
                "Readiness records traced for this report: "
                + ", ".join(report.traced_receiver_readiness_ids),
                styles["Normal"],
            )
        )
    else:
        story.append(Paragraph("No readiness records to trace yet.", styles["Normal"]))

    doc.build(story)
    return output_path
