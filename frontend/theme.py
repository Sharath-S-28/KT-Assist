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

    Brand header strategy:
    - st.logo() with the full logo PNG (cube + name + subtitle).
      CSS overrides Streamlit's hardcoded 2rem height cap on img.stLogo
      so the image renders at a proper sidebar-filling size (~72px).
    - icon_image= shows the cube-only PNG when the sidebar is collapsed.
    - Funnel Sans Variable from Google Fonts applied globally.
    - Frozen Genpact palette + Streamlit padding/toolbar cleanup.

    Safe to call from multiple screens — st.logo() and st.markdown() are
    both idempotent in Streamlit's rendering model.
    """
    import os

    # ── st.logo(): full logo expanded, cube icon collapsed ──
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

    # ── CSS ──
    # Note: img.stLogo height override unlocks Streamlit's hardcoded 2rem cap
    # (largeLogoHeight in theme sizes). We set it to 72px so the full logo
    # image (300x80) renders at a readable size filling the sidebar header.
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

/* Override Streamlit logo height cap — default is 2rem (32px) at size=large.
   Set to auto so the image scales to fill the stSidebarHeader container width,
   with a max-height cap we control instead of Streamlit's hardcoded value. */
img.stLogo {
    height: auto !important;
    max-height: 72px !important;
    width: 100% !important;
    max-width: 100% !important;
    object-fit: contain !important;
    object-position: left center !important;
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
