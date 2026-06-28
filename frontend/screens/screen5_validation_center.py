"""
frontend/screens/screen5_validation_center.py — Screen 5: Validation
Center (Phase 11 / Session 33). [FROZEN] content: coverage gauge +
five-domain breakdown (schemas.dashboard.CoverageDashboard, via
client.get_coverage_dashboard), the gap register (type/severity/
question/status -- models.coverage.GapRecord's object_type/risk_level/
remediation_question/status, surfaced over HTTP for the first time this
session via client.list_gaps / services/routers/gaps.py), and the
Knowledge Sufficient/Insufficient banner keyed off
CoverageDashboard.sufficient.

Gap *resolution* (submitting a response to an open gap) is explicitly
out of scope here -- gaps.router is read-only for Session 33; Session
34's Screen 6 (Gap Resolution Workspace) owns the write path. This
screen only displays the register.

The sufficiency banner does not reuse components.status_banner as-is:
that helper colours off schemas.explanation.Decision ("Ready"/
"Conditionally Ready"/"Not Ready"), a different vocabulary than the
boolean CoverageDashboard.sufficient. Rendering it directly here with
the same frozen READY/NOT_READY colours keeps the visual language
consistent without overloading status_banner's decision contract.
"""

import streamlit as st

from frontend.api_client import ApiClient, ApiError
from frontend.components import coverage_gauge
from frontend.theme import NOT_READY, PAGE_BG, READY, inject_global_css


def _sufficiency_banner(sufficient: bool) -> None:
    color = READY if sufficient else NOT_READY
    label = "Knowledge Sufficient" if sufficient else "Knowledge Insufficient"
    st.markdown(
        f'<div style="background-color:{color};color:{PAGE_BG};'
        f'padding:14px 18px;border-radius:8px;font-size:1.1em;'
        f'font-weight:700;text-align:center;">{label}</div>',
        unsafe_allow_html=True,
    )


def render(client: ApiClient) -> None:
    inject_global_css()
    st.title("Validation Center")

    packages = client.list_packages()
    if not packages:
        st.info("No knowledge packages exist yet.")
        return

    selected_name = st.selectbox("Package", options=[p.name for p in packages])
    package = next(p for p in packages if p.name == selected_name)

    try:
        dashboard = client.get_coverage_dashboard(package.id)
    except ApiError as exc:
        if exc.status_code == 404:
            st.caption("No coverage assessment has run for this package yet.")
            return
        raise

    _sufficiency_banner(dashboard.sufficient)
    st.write("")
    coverage_gauge(dashboard.gauge_value)

    st.subheader("Coverage by Domain")
    st.table(
        [
            {
                "Domain": d.domain,
                "Coverage": f"{d.coverage * 100:.0f}%" if d.coverage is not None else "Not assessed",
            }
            for d in dashboard.domain_breakdown
        ]
    )

    st.subheader("Gap Summary")
    summary_cols = st.columns(5)
    summary_fields = [
        ("Total", dashboard.gap_summary.total),
        ("Open", dashboard.gap_summary.open),
        ("Closed", dashboard.gap_summary.closed),
        ("Critical", dashboard.gap_summary.critical),
        ("High Risk", dashboard.gap_summary.high_risk),
    ]
    for col, (label, value) in zip(summary_cols, summary_fields):
        with col:
            st.metric(label=label, value=value)

    st.subheader("Gap Register")
    gaps = client.list_gaps(package.id)
    if not gaps:
        st.caption("No gaps recorded for this package.")
        return

    st.table(
        [
            {
                "Type": g.object_type,
                "Severity": g.risk_level or "—",
                "Question": g.remediation_question or "—",
                "Status": g.status,
            }
            for g in gaps
        ]
    )
