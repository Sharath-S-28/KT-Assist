"""
frontend/screens/screen1_executive_dashboard.py — Screen 1: Executive
Dashboard (Phase 11 / Session 33). [FROZEN] content: five headline
metrics (Total Programs, Avg Coverage, Avg OIS, Ready, At-Risk), Coverage
Funnel, Readiness Funnel, KT Status Distribution, Risk Summary. Audience:
Leadership. "Not a chatbot" criterion: leads with metrics + funnels and
exposes no free-text prompt surface anywhere on this screen.

Backed entirely by client.get_executive_dashboard() (services/routers/
dashboard.py's /api/dashboards/executive, Phase 10) -- this screen
aggregates already-persisted scores, it computes nothing itself.
"""

import streamlit as st

from frontend.api_client import ApiClient
from frontend.components import metric_card
from frontend.theme import inject_global_css


def render(client: ApiClient) -> None:
    inject_global_css()
    st.title("Executive Dashboard")

    dashboard = client.get_executive_dashboard()

    # [FROZEN] five headline metrics
    cols = st.columns(5)
    with cols[0]:
        metric_card("Total Programs", str(dashboard.total_programs))
    with cols[1]:
        metric_card("Avg Coverage", f"{dashboard.average_coverage * 100:.0f}%")
    with cols[2]:
        metric_card("Avg OIS", f"{dashboard.average_ois:.0f}")
    with cols[3]:
        metric_card("Ready", str(dashboard.ready_count))
    with cols[4]:
        metric_card("At-Risk", str(dashboard.at_risk_count))

    st.divider()

    funnel_col, readiness_col = st.columns(2)
    with funnel_col:
        st.subheader("Coverage Funnel")
        if dashboard.coverage_funnel:
            st.table({"Stage": [s.stage for s in dashboard.coverage_funnel],
                      "Count": [s.count for s in dashboard.coverage_funnel]})
        else:
            st.caption("No programs yet.")
    with readiness_col:
        st.subheader("Readiness Funnel")
        if dashboard.readiness_funnel:
            st.table({"Stage": [s.stage for s in dashboard.readiness_funnel],
                      "Count": [s.count for s in dashboard.readiness_funnel]})
        else:
            st.caption("No receivers assessed yet.")

    st.subheader("KT Status Distribution")
    if dashboard.status_distribution:
        st.bar_chart(dashboard.status_distribution)
    else:
        st.caption("No programs yet.")

    st.subheader("Risk Summary")
    if dashboard.risk_concentration:
        st.table({
            "Domain": [r.domain for r in dashboard.risk_concentration],
            "Open Gaps": [r.open_gaps for r in dashboard.risk_concentration],
            "Critical Gaps": [r.critical_gaps for r in dashboard.risk_concentration],
        })
    else:
        st.caption("No open gaps recorded.")

    if dashboard.programs:
        st.subheader("Programs")
        st.dataframe(
            [
                {
                    "Program": p.name,
                    "Lifecycle State": p.lifecycle_state,
                    "Completion Status": p.completion_status,
                    "Coverage": f"{p.coverage * 100:.0f}%" if p.coverage is not None else "—",
                    "OIS": f"{p.ois:.0f}" if p.ois is not None else "—",
                    "Readiness": p.readiness or "—",
                    "At Risk": "Yes" if p.at_risk else "No",
                }
                for p in dashboard.programs
            ],
            use_container_width=True,
        )
