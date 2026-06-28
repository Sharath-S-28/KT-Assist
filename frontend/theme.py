"""
frontend/theme.py — [FROZEN] colour palette + small Streamlit styling
helpers (Phase 11 / Session 33).

The palette is NOT re-typed from the spec: config.COLORS (Phase 10 /
Session 31's graph_viewer.py already keys off it) turns out to already
be byte-for-byte the spec's frozen palette --
page #FFFFFF / card #FFFAF4 / callout #FFF2DF / nav #282A27 / ink #161916
/ border #444744 / muted #6D706B / ready #3D6B4F / conditional #FFAD28 /
not_ready #FF4F59. This module only renames the keys to the spec's
vocabulary and adds the two decision-status colours config.COLORS
doesn't separately name (they reuse ready/conditional/not_ready).

This module imports nothing from the backend (not even schemas/) -- it
is pure presentation constants, so it is exempt from needing api_client
at all, but it still participates in the same frontend/ boundary guard
(tests/test_frontend_boundary.py) as every other module here.
"""

import streamlit as st

import config

PAGE_BG = config.COLORS["page_background"]
CARD_BG = config.COLORS["card_background"]
CALLOUT_BG = config.COLORS["callout_background"]
NAV_BG = config.COLORS["nav_secondary"]
INK = config.COLORS["primary_text"]
BORDER = config.COLORS["borders"]
MUTED = config.COLORS["placeholder"]
READY = config.COLORS["success_ready"]
CONDITIONAL = config.COLORS["warning_conditional"]
NOT_READY = config.COLORS["error_not_ready"]

# Decision -> colour, reusing the exact stored values from
# config.READINESS_DECISIONS / schemas.explanation.Decision rather than
# inventing a parallel lowercase vocabulary.
DECISION_COLORS: dict[str, str] = {
    "Ready": READY,
    "Conditionally Ready": CONDITIONAL,
    "Not Ready": NOT_READY,
}

# CompetencyIndicator.indicator ("pass"/"fail"/"warning", schemas.dashboard)
INDICATOR_COLORS: dict[str, str] = {
    "pass": READY,
    "fail": NOT_READY,
    "warning": CONDITIONAL,
}


def decision_color(decision: str | None) -> str:
    return DECISION_COLORS.get(decision, MUTED)


def inject_global_css() -> None:
    """Apply the frozen palette to the page background, sidebar nav, and
    Streamlit's default card-like containers. Called once per screen."""
    st.markdown(
        f"""
        <style>
        .stApp {{
            background-color: {PAGE_BG};
            color: {INK};
        }}
        section[data-testid="stSidebar"] {{
            background-color: {NAV_BG};
        }}
        section[data-testid="stSidebar"] * {{
            color: {PAGE_BG} !important;
        }}
        div[data-testid="stMetric"] {{
            background-color: {CARD_BG};
            border: 1px solid {BORDER};
            border-radius: 8px;
            padding: 12px;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def badge_html(label: str, color: str) -> str:
    """A small pill-shaped HTML badge in the given colour, used for
    decision/competency status anywhere a screen needs one inline."""
    return (
        f'<span style="background-color:{color};color:{PAGE_BG};'
        f'padding:2px 10px;border-radius:12px;font-size:0.85em;'
        f'font-weight:600;">{label}</span>'
    )


def callout_html(text: str) -> str:
    return (
        f'<div style="background-color:{CALLOUT_BG};border:1px solid {BORDER};'
        f'border-radius:8px;padding:10px 14px;color:{INK};">{text}</div>'
    )
