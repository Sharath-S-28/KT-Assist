"""
frontend/guided_demo/executive_dashboard.py — Executive Command Center
(UI Phase 1).

Portfolio-level storytelling screen: deterministic synthetic fixture
(frontend/guided_demo/portfolio_fixture.py) plus the one real,
validated PBI Dashboard hierarchical demo case overlaid with its live
backend state (frontend.api_client.ApiClient.get_demo_summary()).
Every KPI/chart/table here derives from the same
portfolio_fixture.get_all_cases() list -- no parallel numbers.
"""

import streamlit as st

from frontend.api_client import ApiClient
from frontend.components import metric_card
from frontend.guided_demo import portfolio_fixture as pf
from frontend.theme import BORDER, CARD_BG, MUTED, badge_html, decision_color, inject_global_css

_RISK_BADGE_COLORS = {
    pf.RISK_CRITICAL: "#FF4F59",
    pf.RISK_HIGH: "#FFAD28",
    pf.RISK_MEDIUM: "#6D706B",
    pf.RISK_LOW: "#3D6B4F",
}


def _readiness_badge_color(status: str) -> str:
    if status in pf.RECEIVER_OUTCOME_STATUSES:
        return decision_color(status)
    if status == "Mixed Readiness":
        return "#FFAD28"
    return MUTED


@st.cache_data(show_spinner=False)
def _load_static_cases() -> list[pf.TransitionCase]:
    """Streamlit caching is safe here: this returns only the static
    fixture, never the live-overlaid PBI row -- the real state is
    fetched fresh on every render (see render()) and merged in after
    the cache lookup, so a backend change is never hidden behind a
    stale cache."""
    return pf.get_all_cases()


def render(client: ApiClient) -> None:
    inject_global_css()

    st.title("Knowledge Transition Command Center")
    st.caption("Enterprise visibility into knowledge assurance, transition risk, and receiver readiness")
    st.markdown(
        badge_html("Portfolio values and operational exposure shown for demonstration purposes", MUTED),
        unsafe_allow_html=True,
    )
    st.write("")

    try:
        summary = client.get_demo_summary()
    except Exception:
        summary = None

    cases = pf.apply_real_pbi_state(_load_static_cases(), summary)

    # -- B. KPI strip --------------------------------------------------------
    cols = st.columns(6)
    with cols[0]:
        metric_card("Active Transitions", str(pf.total_active_transitions(cases)))
    with cols[1]:
        metric_card("Knowledge-Assured", str(pf.total_knowledge_assured(cases)))
    with cols[2]:
        metric_card("Receivers Assessed", str(pf.total_receivers_assessed(cases)))
    with cols[3]:
        dist = pf.readiness_distribution(cases)
        metric_card("Ready", str(dist[pf.READY]), sublabel=f"{dist[pf.CONDITIONALLY_READY]} conditional")
    with cols[4]:
        metric_card("Critical Transition Risks", str(pf.total_critical_risk_transitions(cases)))
    with cols[5]:
        exposure = pf.total_operational_exposure(cases)
        metric_card("Est. Operational Exposure", f"${exposure / 1_000_000:.2f}M")

    st.divider()

    # -- C. Portfolio visuals -------------------------------------------------
    chart_col1, chart_col2 = st.columns(2)
    with chart_col1:
        st.subheader("Readiness Distribution")
        dist = pf.readiness_distribution(cases)
        st.bar_chart(dist)
    with chart_col2:
        st.subheader("Assurance Status Distribution")
        st.bar_chart(pf.assurance_status_distribution(cases))

    st.subheader("Operational Exposure by Business Unit")
    bu_summary = pf.business_unit_summary(cases)
    st.bar_chart({unit: data["operational_exposure"] for unit, data in bu_summary.items()})

    st.divider()

    # -- D. Executive Attention panel -----------------------------------------
    st.subheader("Executive Attention")
    attention_items = pf.get_executive_attention_items(cases)
    if not attention_items:
        st.caption("No transitions currently require executive attention.")
    else:
        for case in attention_items:
            badge_color = _RISK_BADGE_COLORS.get(case.risk_level, MUTED)
            st.markdown(
                f"""
                <div style="background-color:{CARD_BG};border:1px solid {BORDER};
                border-radius:8px;padding:12px 16px;margin-bottom:8px;">
                    <div style="font-weight:700;font-size:1.05em;">{case.transition_name}
                        &nbsp;{badge_html(case.risk_level, badge_color)}</div>
                    <div style="margin-top:4px;">{case.business_unit} &nbsp;|&nbsp;
                        Stage: {case.current_stage}</div>
                    <div style="margin-top:6px;">{pf.attention_reason(case)}</div>
                    <div style="margin-top:4px;color:{MUTED};">Action: {pf.attention_action(case)}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.divider()

    # -- E. Transition Portfolio table -----------------------------------------
    st.subheader("Transition Portfolio")
    st.dataframe(
        [
            {
                "Transition": (("⭐ " if c.is_real_case else "") + c.transition_name),
                "Business Unit": c.business_unit,
                "Knowledge Provider": c.knowledge_provider,
                "Receivers": f"{c.receivers_assessed}/{c.receiver_count}",
                "Knowledge Assurance": c.knowledge_assurance_status,
                "Readiness": c.readiness_status,
                "Risk": c.risk_level,
                "Operational Exposure": f"${c.operational_exposure:,}",
                "Current Stage": c.current_stage,
            }
            for c in cases
        ],
        use_container_width=True,
        hide_index=True,
    )

    st.caption("⭐ = real, validated hierarchical knowledge-assurance demo case")

    st.write("")
    st.subheader("Enter Guided Demo Case Shell")
    case_names = {c.case_id: (("⭐ " if c.is_real_case else "") + c.transition_name) for c in cases}
    selected_id = st.selectbox(
        "Select a transition case",
        options=list(case_names.keys()),
        format_func=lambda cid: case_names[cid],
        index=list(case_names.keys()).index(pf.PBI_CASE_ID),
    )
    if st.button("Open Guided Demo Case Shell →", type="primary"):
        st.session_state["guided_demo_selected_case_id"] = selected_id
        guided_shell_page = st.session_state.get("_nav_pages", {}).get("guided_shell")
        if guided_shell_page is not None:
            st.switch_page(guided_shell_page)
        else:
            st.info("Select **Guided Demo Case Shell** in the sidebar to continue.")
