"""
frontend/screens/screen8_readiness_scorecard.py — Screen 8: Readiness
Scorecard (Phase 11 / Session 34). Confirmed against multiple independent
inline docstring references found pre-compaction (schemas/dashboard.py's
"[FROZEN] Screen 8 Pass/Fail/Warning", services/readiness_dashboard_service.py's
"Chunk 8 Screen 8", frontend/components/__init__.py's "All 12 competency
Pass/Fail/Warning indicators (Screen 8)").

[FROZEN] content, per schemas.dashboard.ReadinessDashboard: OIS score,
readiness decision (Ready/Conditionally Ready/Not Ready), certification
tier, the 4 pillar scores, and all 12 competency Pass/Fail/Warning
indicators -- reuses components.competency_grid, the widget Session 33
already built for exactly this shape but that no Session 33 screen ended
up consuming (ReceiverReadiness is receiver-scoped, not package-scoped,
so it has no natural home on Screens 1-5).

Single-receiver scorecard: per readiness_dashboard_service.py's own
ruling, a receiver can be assessed against more than one package, so
client.get_readiness_dashboard(participant_id) always returns that
receiver's MOST RECENT readiness row. This screen surfaces that latest
row only; it does not offer a per-package history view (no endpoint
exists for that).
"""

import streamlit as st

from frontend.api_client import ApiClient, ApiError
from frontend.components import competency_grid, status_banner
from frontend.theme import inject_global_css


def render(client: ApiClient) -> None:
    inject_global_css()
    st.title("Readiness Scorecard")

    participants = client.list_participants()
    receivers = [p for p in participants if p.participant_type == "Receiver"]
    if not receivers:
        st.info("No receivers exist yet. Add one on the Participant Management screen.")
        return

    selected_name = st.selectbox("Receiver", options=[p.name for p in receivers])
    receiver = next(p for p in receivers if p.name == selected_name)

    try:
        dashboard = client.get_readiness_dashboard(receiver.id)
    except ApiError as exc:
        if exc.status_code == 404:
            st.caption("No readiness assessment has run for this receiver yet.")
            return
        raise

    status_banner(dashboard.readiness_status)
    st.write("")

    cols = st.columns(3)
    with cols[0]:
        st.metric("OIS Score", f"{dashboard.ois:.1f}")
    with cols[1]:
        st.metric("Certification", dashboard.certification or "—")
    with cols[2]:
        st.metric("Package", dashboard.package_id[:8] + "…")

    st.subheader("Pillar Scores")
    st.table([{"Pillar": p.name, "Score": f"{p.score:.1f}"} for p in dashboard.pillars])

    st.subheader("Competency Indicators")
    competency_grid(dashboard.competencies)

    st.caption(f"Receiver Readiness ID: {dashboard.receiver_readiness_id}")
