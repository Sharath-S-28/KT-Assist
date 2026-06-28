"""
frontend/screens/screen6_gap_resolution_workspace.py — Screen 6: Gap
Resolution Workspace (Phase 11 / Session 34).

Owns the write path Screen 5 (Validation Center) explicitly deferred:
selecting one Open gap from a package's register and submitting a
free-text response to its remediation_question. Posts through
client.submit_gap_response (frontend/api_client.py), which hits
POST /api/packages/{package_id}/gaps/{gap_id}/responses
(services/routers/gaps.py) -- a single call that, server-side, composes
capture_gap_response -> interpret_gap_response -> close_gap end to end
(capture, interpret, apply-to-graph, recalculate-coverage). This screen
does none of that composition itself; it only renders the gap list,
collects the raw_text, and displays the GapResolutionResult the backend
returns (previous/new coverage, version bump, sufficiency).

Only gaps with status == "Open" are offered for resolution -- Resolved/
Waived gaps have nothing left to submit a response to. After a
successful submission the gap disappears from the open-gap selector on
rerun (its status flips to "Resolved" server-side), giving an implicit
confirmation beyond the success message.
"""

import streamlit as st

from frontend.api_client import ApiClient, ApiError
from frontend.theme import inject_global_css


def render(client: ApiClient) -> None:
    inject_global_css()
    st.title("Gap Resolution Workspace")

    packages = client.list_packages()
    if not packages:
        st.info("No knowledge packages exist yet.")
        return

    selected_name = st.selectbox("Package", options=[p.name for p in packages])
    package = next(p for p in packages if p.name == selected_name)

    gaps = client.list_gaps(package.id)
    open_gaps = [g for g in gaps if g.status == "Open"]

    if not open_gaps:
        st.success("No open gaps for this package.")
        return

    gap_labels = [f"{g.object_type}: {g.description}" for g in open_gaps]
    selected_label = st.selectbox("Open Gap", options=gap_labels)
    gap = open_gaps[gap_labels.index(selected_label)]

    st.caption(f"Severity: {gap.risk_level or '—'}")
    st.write(f"**Remediation question:** {gap.remediation_question or '—'}")

    raw_text = st.text_area("Your response", key=f"gap-response-{gap.id}")

    if st.button("Submit Response", disabled=not raw_text.strip()):
        try:
            result = client.submit_gap_response(package.id, gap.id, raw_text=raw_text)
        except ApiError as exc:
            st.error(f"Submission failed: {exc.message}")
            return

        st.success(f"Gap resolved. Status: {result.gap_status}")
        cols = st.columns(3)
        with cols[0]:
            st.metric("Coverage", f"{result.new_coverage_score * 100:.0f}%", delta=f"{result.coverage_delta * 100:+.0f}%")
        with cols[1]:
            st.metric("Graph Version", result.new_version, delta=result.new_version - result.previous_version)
        with cols[2]:
            st.metric("Sufficient", "Yes" if result.sufficient else "No")
        st.caption(result.change_summary)
        st.rerun()
