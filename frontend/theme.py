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
    """Apply the Genpact brand to the entire app.

    Covers:
    - st.logo() with the KT Assist logo PNG — Streamlit's official API for
      placing branding above the sidebar nav. Works correctly when the sidebar
      is collapsed/expanded (no CSS hacks needed).
    - Funnel Sans Variable (Genpact brand typeface) via Google Fonts.
    - Frozen Genpact colour palette on page background, sidebar, and cards.
    - Removes Streamlit's default top padding on the main content area.

    Safe to call from multiple screens — logo and font links are idempotent
    in Streamlit's rendering model.
    """
    import os

    # ── st.logo() — official Streamlit API for sidebar branding ──
    # image: full logo shown when sidebar is open.
    # icon_image: cube-only icon shown when sidebar is collapsed.
    logo_path = os.path.join(os.path.dirname(__file__), "..", "assets", "kt_logo.png")
    icon_path = os.path.join(os.path.dirname(__file__), "..", "assets", "kt_logo_icon.png")
    logo_path = os.path.normpath(logo_path)
    icon_path = os.path.normpath(icon_path)
    if os.path.exists(logo_path):
        try:
            st.logo(
                logo_path,
                size="large",
                icon_image=icon_path if os.path.exists(icon_path) else None,
            )
        except TypeError:
            st.logo(logo_path)

    # ── Google Fonts ──
    st.markdown(
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
        '<link href="https://fonts.googleapis.com/css2?family=Funnel+Sans:wght@300..800&display=swap"'
        ' rel="stylesheet">',
        unsafe_allow_html=True,
    )

    # ── CSS — plain string with .replace() for colour values ──
    css = """
<style>
html, body, [class*="css"], .stApp,
.stMarkdown, .stText, h1, h2, h3, h4, h5, h6,
.stButton > button, .stSelectbox, .stTextInput,
.stMetric, label, .stDataFrame,
div[data-testid="stSidebarNav"] * {
    font-family: 'Funnel Sans', sans-serif !important;
}
.stApp {
    background-color: PAGE_BG_VAL;
    color: INK_VAL;
}
section[data-testid="stSidebar"] {
    background-color: NAV_BG_VAL;
}
section[data-testid="stSidebar"] * {
    color: PAGE_BG_VAL !important;
    font-family: 'Funnel Sans', sans-serif !important;
}

/* Remove Streamlit default toolbar and top padding on main content */
.stApp > header { display: none; }
div[data-testid="stAppViewContainer"] > section[data-testid="stMain"] > div {
    padding-top: 1.5rem !important;
}

/* Active nav item highlight */
div[data-testid="stSidebarNav"] a:hover {
    background-color: rgba(255,173,40,0.12) !important;
    border-radius: 6px;
}
div[data-testid="stSidebarNav"] a[aria-current="page"] {
    background-color: rgba(255,173,40,0.18) !important;
    border-left: 3px solid #FFAD28 !important;
    border-radius: 0 6px 6px 0;
}

/* Metric cards */
div[data-testid="stMetric"] {
    background-color: CARD_BG_VAL;
    border: 1px solid BORDER_VAL;
    border-radius: 8px;
    padding: 12px;
}
</style>
""".replace("PAGE_BG_VAL", PAGE_BG).replace("INK_VAL", INK).replace(
        "NAV_BG_VAL", NAV_BG
    ).replace("CARD_BG_VAL", CARD_BG).replace("BORDER_VAL", BORDER)

    st.markdown(css, unsafe_allow_html=True)


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
