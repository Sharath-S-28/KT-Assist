"""
frontend/guided_demo/guided_shell.py — Guided Demo Case Shell
(UI Phase 1).

Navigation shell for the real, validated PBI Dashboard hierarchical
demo case. The persisted backend DemoJourneyState (via
ApiClient.get_demo_state()/get_demo_summary()) is the sole source of
truth for lifecycle progress -- Streamlit session_state here holds
presentation-only state (which tab/expander is open), never a second
copy of the journey stage.

The single-click "advance" actions below call the already-complete,
already-tested demo orchestration API (services/demo/hierarchical_demo_orchestrator.py
via services/routers/demo_hierarchical.py) exactly as a CLI/test would
-- there is no per-gap Q&A UI, no per-scenario response builder, no
object explorer here. Those detailed lifecycle screens are explicitly
UI Phase 2/3 work; this shell only sequences the same deterministic,
already-proven checkpoints the offline replay proof exercises.
"""

import streamlit as st

from frontend.api_client import ApiClient, ApiError
from frontend.guided_demo import lifecycle_scenes, portfolio_fixture as pf
from frontend.theme import MUTED, badge_html, decision_color, inject_global_css

# Conceptual 7-stage narrative (task spec) mapped onto the real 6
# backend stages (models.demo_journey.DEMO_JOURNEY_STAGES) -- labels
# only; the actual stage NAME driving all logic always comes from the
# API, never invented here. ASSESSMENT_COMPLETE is split into two
# conceptual points (Receiver Assessment in progress / Readiness
# Decision reached) using the real receivers-assessed count, not a new
# backend stage.
_CONCEPTUAL_STAGES = [
    "Knowledge Intake",
    "Knowledge Discovery",
    "Knowledge Assurance",
    "Gap Closure",
    "Assurance Result",
    "Receiver Assessment",
    "Readiness Decision",
]

_STAGE_TO_CONCEPTUAL_INDEX = {
    "START": 0,
    "INGESTED": 1,
    "VALIDATED": 2,
    "ENRICHING": 3,
    "ASSURANCE_COMPLETE": 4,
}


def _conceptual_index(stage: str, receivers_assessed: int, receiver_count: int) -> int:
    if stage == "ASSESSMENT_COMPLETE":
        return 6 if receivers_assessed >= receiver_count and receiver_count > 0 else 5
    if stage == "ASSURANCE_COMPLETE":
        return 5 if receivers_assessed > 0 else 4
    return _STAGE_TO_CONCEPTUAL_INDEX.get(stage, 0)


def _resume_action_for_stage(stage: str) -> str:
    return {
        "START": "Begin Knowledge Intake",
        "INGESTED": "Resume at Knowledge Discovery",
        "VALIDATED": "Resume Gap Closure",
        "ENRICHING": "Resume Gap Closure",
        "ASSURANCE_COMPLETE": "Continue to Receiver Assessment",
        "ASSESSMENT_COMPLETE": "View Readiness Decision",
    }.get(stage, "Continue")


def _progress_tracker(current_index: int) -> None:
    columns = st.columns(len(_CONCEPTUAL_STAGES))
    for i, (col, label) in enumerate(zip(columns, _CONCEPTUAL_STAGES)):
        reached = i <= current_index
        color = "#3D6B4F" if reached else MUTED
        weight = "700" if i == current_index else "400"
        with col:
            st.markdown(
                f'<div style="text-align:center;color:{color};'
                f'font-weight:{weight};font-size:0.78em;">{label}</div>',
                unsafe_allow_html=True,
            )


def _run_advance_action(client: ApiClient, stage: str) -> None:
    try:
        if stage == "START":
            client.ingest_demo_hierarchical()
        elif stage == "INGESTED":
            client.validate_demo_hierarchical()
        elif stage in ("VALIDATED", "ENRICHING"):
            client.advance_demo_enrichment(max_rounds=50)
            client.complete_demo_assurance()
        elif stage == "ASSURANCE_COMPLETE":
            summary = client.get_demo_summary()
            for participant_id in summary.get("receivers", {}):
                client.assess_demo_receiver(participant_id)
    except ApiError as exc:
        st.error(f"Could not advance the demo: {exc.message}")
        return
    st.rerun()


def _render_synthetic_case_detail(case: pf.TransitionCase) -> None:
    """Lightweight, static detail view for a non-PBI portfolio case --
    included for executive portfolio demonstration only. Never calls
    the demo hierarchical API or attempts to run any real lifecycle
    operation for a synthetic case."""
    st.title(case.transition_name)
    st.caption(f"{case.business_unit} &nbsp;|&nbsp; Knowledge provider: {case.knowledge_provider}",
               unsafe_allow_html=True)
    st.info(
        "This transition is part of the executive portfolio demonstration. "
        "It is illustrative synthetic data, not a live hierarchical knowledge-assurance case."
    )
    cols = st.columns(4)
    with cols[0]:
        st.metric("Receivers", f"{case.receivers_assessed}/{case.receiver_count}")
    with cols[1]:
        st.metric("Knowledge Assurance", case.knowledge_assurance_status)
    with cols[2]:
        st.metric("Readiness", case.readiness_status)
    with cols[3]:
        st.metric("Risk Level", case.risk_level)
    st.markdown(f"**Current stage:** {case.current_stage}")
    st.markdown(f"**Estimated operational exposure:** ${case.operational_exposure:,}")
    st.caption(
        "Only the Power BI Regional Sales Dashboards case is backed by the real, validated "
        "hierarchical knowledge-assurance demo lifecycle."
    )


def render(client: ApiClient) -> None:
    inject_global_css()

    selected_case_id = st.session_state.get("guided_demo_selected_case_id", pf.PBI_CASE_ID)
    static_case = next((c for c in pf.get_all_cases() if c.case_id == selected_case_id), None)
    if static_case is None:
        static_case = next(c for c in pf.get_all_cases() if c.case_id == pf.PBI_CASE_ID)

    if not static_case.is_real_case:
        _render_synthetic_case_detail(static_case)
        return

    try:
        summary = client.get_demo_summary()
    except Exception as exc:
        st.title("Guided Demo Case Shell")
        st.error(f"Could not reach the demo API: {exc}")
        return

    stage = summary.get("stage", "START")
    receivers = summary.get("receivers", {})
    receiver_count = len(receivers) or 3
    assessed = [r for r in receivers.values() if r.get("status") == "assessed"]

    st.title(static_case.transition_name)
    st.caption(
        f"{static_case.business_unit} &nbsp;|&nbsp; Knowledge provider: {static_case.knowledge_provider} "
        f"&nbsp;|&nbsp; Receiver group: {', '.join(r['name'] for r in receivers.values()) or '3 pinned receivers'}",
        unsafe_allow_html=True,
    )
    st.write("")

    _progress_tracker(_conceptual_index(stage, len(assessed), receiver_count))
    st.write("")

    if assessed:
        st.markdown("**Receiver Outcomes**")
        outcome_cols = st.columns(len(assessed))
        for col, r in zip(outcome_cols, assessed):
            with col:
                color = decision_color(r["final_decision"])
                st.markdown(
                    f'{r["name"]}<br>{badge_html(f"{r["final_decision"]} · OIS {r["ois_score"]:.1f}", color)}',
                    unsafe_allow_html=True,
                )

    st.divider()

    tab_labels = [
        "1. Knowledge Intake", "2. Knowledge Discovery", "3. Knowledge Assurance",
        "4. Gap Closure", "5. Assurance Result", "6. Receiver Assessment", "7. Readiness Decision",
    ]
    tabs = st.tabs(tab_labels)

    with tabs[0]:
        lifecycle_scenes.render_knowledge_intake(client, summary)
    with tabs[1]:
        lifecycle_scenes.render_knowledge_discovery(client, summary)
    with tabs[2]:
        lifecycle_scenes.render_knowledge_assurance(client, summary)
    with tabs[3]:
        lifecycle_scenes.render_gap_closure(client, summary)
    with tabs[4]:
        lifecycle_scenes.render_assurance_result(client, summary)
    with tabs[5]:
        st.info(
            "Receiver Assessment is implemented in UI Phase 3. The real hierarchical lifecycle "
            "already supports assessing Priya, Receiver B, and Receiver C — this shell will surface "
            "that experience in the next phase."
        )
        if stage == "ASSURANCE_COMPLETE":
            if st.button("Continue to Receiver Assessment", type="primary", key="stub_assess_all"):
                _run_advance_action(client, stage)
    with tabs[6]:
        st.info("Readiness Decision is implemented in UI Phase 3.")
        if assessed:
            st.caption(f"{len(assessed)} of {receiver_count} receivers already assessed against the real KRA pipeline.")
