"""
frontend/screens/screen10_kt_assurance_report.py — Screen 10: KT Assurance
Report (Phase 11 / Session 34).

Reconstruction note: like Screen 7, the original Phase 11 spec text for
Screen 10 was lost to context compaction and never persisted to disk.
Ruled here from the same "client method exists, no screen consumes it"
evidence pattern that fixed Screen 7: frontend/api_client.py has carried
get_assurance_report / export_assurance_report_pdf /
export_assurance_report_pptx since Session 33 (backing
schemas.assurance_report.AssuranceReport, Phase 10 / Session 32's "Master
Spec Appendix C" KT Assurance Report), and no screen built across
Sessions 33-34 has ever called any of them. With Screens 1-9 now
accounted for against every other backend capability, the assurance
report is the only remaining unconsumed surface of comparable weight --
and "Screen 10" as the final screen in a ten-screen spec matching the
final, program-level rollup document (cover/summary/coverage/gaps/
readiness/competency/certification/recommendations/traceability/metadata
-- AssuranceReport's own ten Appendix-C sections) fits a closing screen
far better than any partial or duplicate view of data Screens 1-9
already show individually.

Rendering choice: AssuranceReport's ten sections are dense (nested lists
of dashboards, dicts of recommendations); this screen renders each
section under its own st.expander rather than flattening everything to
the page at once, so the report stays scannable. PDF/PPTX export buttons
call the two byte-returning client methods directly and hand the result
to st.download_button -- no local rendering of the binary, consistent
with screens 1-9 never touching anything but typed Pydantic models from
api_client.
"""

import streamlit as st

from frontend.api_client import ApiClient, ApiError
from frontend.theme import inject_global_css


def render(client: ApiClient) -> None:
    inject_global_css()
    st.title("KT Assurance Report")

    programs = client.list_programs()
    if not programs:
        st.info("No programs exist yet.")
        return

    program_name = st.selectbox("Program", options=[p.name for p in programs])
    program = next(p for p in programs if p.name == program_name)

    try:
        report = client.get_assurance_report(program.id)
    except ApiError as exc:
        if exc.status_code == 404:
            st.caption("No assurance report can be generated yet for this program.")
            return
        raise

    st.caption(f"Report {report.report_id} — generated {report.generated_at}")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Export PDF"):
            pdf_bytes = client.export_assurance_report_pdf(program.id)
            st.download_button(
                "Download PDF", data=pdf_bytes, file_name=f"{program.name}_assurance_report.pdf", mime="application/pdf"
            )
    with col2:
        if st.button("Export PPTX"):
            pptx_bytes = client.export_assurance_report_pptx(program.id)
            st.download_button(
                "Download PPTX",
                data=pptx_bytes,
                file_name=f"{program.name}_assurance_report.pptx",
                mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            )

    with st.expander("1-2. Cover & Executive Summary", expanded=True):
        health = report.program_health
        st.write(f"**{health.name}**")
        st.write(f"At risk: {'Yes' if health.at_risk else 'No'}")
        if health.readiness is not None:
            st.write(f"Readiness: {health.readiness}")

    with st.expander("3. Coverage Assessment"):
        if not report.coverage_by_package:
            st.caption("No coverage data yet.")
        for cov in report.coverage_by_package:
            st.write(f"Package {cov.package_id[:8]}… — coverage {cov.coverage * 100:.0f}% (sufficient: {cov.sufficient})")

    with st.expander("4. Gap & Risk Analysis"):
        gs = report.gap_summary
        st.write(f"Total gaps: {gs.total} (open {gs.open}, closed {gs.closed}, critical {gs.critical}, high-risk {gs.high_risk})")
        for cell in report.risk_concentration:
            st.write(f"- {cell.domain}: {cell.open_gaps} open, {cell.critical_gaps} critical")

    with st.expander("5. Receiver Readiness Summary"):
        if not report.readiness_by_receiver:
            st.caption("No receivers assessed yet.")
        for dashboard in report.readiness_by_receiver:
            st.write(f"{dashboard.receiver_name}: {dashboard.readiness_status} (OIS {dashboard.ois:.1f})")

    with st.expander("6. Competency Assessment Detail"):
        cs = report.competency_summary
        st.write(f"Total {cs.total} — passed {cs.passed}, failed {cs.failed}, warning {cs.warning}")

    with st.expander("7. Certification & Sign-off Status"):
        st.write(f"Overall decision: {report.overall_decision or '—'}")
        for cert in report.certifications:
            st.write(f"- {cert.receiver_name}: {cert.readiness_status} ({cert.certification or '—'})")

    with st.expander("8. Recommendations"):
        if not report.recommendations_by_receiver:
            st.caption("No outstanding recommendations.")
        for receiver_id, recs in report.recommendations_by_receiver.items():
            st.write(f"Receiver {receiver_id[:8]}…")
            for rec in recs:
                st.write(f"  - {rec.competency_name}: {', '.join(rec.actions)}")

    with st.expander("9. Traceability Appendix"):
        if not report.traced_receiver_readiness_ids:
            st.caption("No traceability records yet.")
        for rid in report.traced_receiver_readiness_ids:
            st.write(f"- {rid}")
