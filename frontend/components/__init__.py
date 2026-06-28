"""
frontend/components — small reusable Streamlit rendering helpers (Phase 11
/ Session 33).

Every function here takes only plain values or api_client return types
(KTProgramRead, KnowledgePackageRead, CompetencyIndicator, ...) -- never
a backend ORM/service object -- and renders Streamlit widgets using the
[FROZEN] palette from frontend/theme.py. This module participates in the
same frontend/ boundary guard (tests/test_frontend_boundary.py) as every
other module here: it imports streamlit, frontend.theme, and Python
stdlib only.
"""

import streamlit as st

from frontend.theme import (
    BORDER,
    CARD_BG,
    INDICATOR_COLORS,
    MUTED,
    badge_html,
    decision_color,
)

# config.LIFECYCLE_STATES, mirrored here as a plain literal list rather
# than imported from config -- frontend/ may not import config (it sits
# beside services/models/database as a backend-internal module: every
# other backend constant the frontend needs arrives already resolved on
# an api_client response, e.g. KTProgramRead.lifecycle_state). This one
# ordered list is display-only scaffolding for the tracker widget, not a
# rule the frontend enforces -- the backend's workflow engine (Phase 2 /
# Session 4) remains the sole source of truth for which transitions are
# legal.
LIFECYCLE_STAGES: list[str] = [
    "Draft",
    "Knowledge Capture",
    "Knowledge Validation",
    "Gap Resolution",
    "Assessment",
    "Ready",
    "Completed",
]


def metric_card(label: str, value: str, sublabel: str | None = None) -> None:
    """One headline metric (Screen 1's Total Programs / Avg Coverage /
    Avg OIS / Ready / At-Risk row). Built on st.metric so it picks up the
    card-like styling theme.inject_global_css already applies to
    stMetric containers."""
    st.metric(label=label, value=value, delta=sublabel, delta_color="off")


def status_banner(decision: str | None) -> None:
    """READY / CONDITIONALLY READY / NOT READY banner (Screen 5's
    Knowledge Sufficient/Insufficient banner reuses this with its own
    text), coloured from the frozen palette via theme.decision_color."""
    color = decision_color(decision)
    label = decision if decision else "Not Yet Assessed"
    st.markdown(
        f'<div style="background-color:{color};color:#FFFFFF;'
        f'padding:14px 18px;border-radius:8px;font-size:1.1em;'
        f'font-weight:700;text-align:center;">{label}</div>',
        unsafe_allow_html=True,
    )


def coverage_gauge(value: float) -> None:
    """0-100 coverage gauge (Screen 5/8). Streamlit has no native gauge
    widget, so this renders st.progress (0.0-1.0) plus the numeric
    readout -- no third-party charting dependency for one bar."""
    clamped = max(0.0, min(100.0, value))
    st.progress(clamped / 100.0, text=f"Coverage: {clamped:.0f}%")


def lifecycle_tracker(current_state: str) -> None:
    """Draft -> Knowledge Capture -> ... -> Completed horizontal tracker
    (Screen 2). Stages at or before current_state render filled; later
    stages render muted."""
    try:
        current_index = LIFECYCLE_STAGES.index(current_state)
    except ValueError:
        current_index = -1  # unrecognized state: render everything muted rather than crash

    columns = st.columns(len(LIFECYCLE_STAGES))
    for i, (col, stage) in enumerate(zip(columns, LIFECYCLE_STAGES)):
        reached = i <= current_index
        color = "#3D6B4F" if reached else MUTED
        weight = "700" if i == current_index else "400"
        with col:
            st.markdown(
                f'<div style="text-align:center;color:{color};'
                f'font-weight:{weight};font-size:0.8em;">{stage}</div>',
                unsafe_allow_html=True,
            )


def package_card(name: str, coverage: float | None, open_gaps: int, status: str, readiness: str | None) -> None:
    """One package summary card on Screen 2 (coverage, open gaps, status,
    readiness)."""
    coverage_text = f"{coverage * 100:.0f}%" if coverage is not None else "Not assessed"
    readiness_badge = badge_html(readiness or "Not Assessed", decision_color(readiness))
    st.markdown(
        f"""
        <div style="background-color:{CARD_BG};border:1px solid {BORDER};
        border-radius:8px;padding:12px 16px;margin-bottom:8px;">
            <div style="font-weight:700;font-size:1.05em;">{name}</div>
            <div style="margin-top:4px;">Coverage: {coverage_text} &nbsp;|&nbsp;
            Open Gaps: {open_gaps} &nbsp;|&nbsp; Status: {status}</div>
            <div style="margin-top:6px;">{readiness_badge}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def competency_grid(competencies: list) -> None:
    """All 12 competency Pass/Fail/Warning indicators (Screen 8).
    `competencies` is a list of schemas.dashboard.CompetencyIndicator
    (or anything with the same competency_id/name/score/is_critical/
    indicator attributes)."""
    columns = st.columns(3)
    for i, competency in enumerate(competencies):
        color = INDICATOR_COLORS.get(competency.indicator, MUTED)
        critical_marker = " *" if competency.is_critical else ""
        with columns[i % 3]:
            st.markdown(
                f'<div style="background-color:{CARD_BG};border:1px solid {BORDER};'
                f'border-radius:6px;padding:8px;margin-bottom:8px;">'
                f'<div style="font-weight:600;">{competency.name}{critical_marker}</div>'
                f'<div>{badge_html(f"{competency.score:.0f}", color)}</div>'
                f"</div>",
                unsafe_allow_html=True,
            )
