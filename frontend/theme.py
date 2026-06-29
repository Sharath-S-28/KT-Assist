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
    - Funnel Sans Variable (Genpact brand typeface) from Google Fonts,
      applied globally to all Streamlit text, headings, inputs, and labels.
    - Frozen Genpact colour palette on page background, sidebar, and cards.
    - Sidebar brand header: geometric G cube SVG + product name + full form.

    Safe to call from multiple screens -- guarded by st.session_state so the
    sidebar header HTML is only injected once per session render pass.
    """
    # Guard: only inject the brand header once per page render to avoid
    # stacking duplicate header blocks when multiple screens call this.
    already_injected = st.session_state.get("_kt_css_injected", False)
    st.session_state["_kt_css_injected"] = True

    # Genpact G cube — isometric 3D line-art with G-notch cutout,
    # built from the brand guide's logo geometry (Brand Playbook p.27/36).
    # Stroke colour = Sunrise Gold (#FFAD28) to stand out on Midnight nav.
    cube_svg = """
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"
         width="44" height="44" style="flex-shrink:0;display:block;">
      <!-- Top face (diamond) -->
      <polygon points="50,8 88,29 50,50 12,29"
               fill="none" stroke="#FFAD28" stroke-width="2.5"
               stroke-linejoin="round"/>
      <!-- Left face -->
      <polygon points="12,29 12,71 50,92 50,50"
               fill="none" stroke="#FFAD28" stroke-width="2.5"
               stroke-linejoin="round"/>
      <!-- Right face -->
      <polygon points="88,29 88,71 50,92 50,50"
               fill="none" stroke="#FFAD28" stroke-width="2.5"
               stroke-linejoin="round"/>
      <!-- G-notch on left face: outer cutout -->
      <polyline points="24,40 24,78 44,89 44,60 36,55 36,68 28,64 28,44"
                fill="none" stroke="#FFAD28" stroke-width="2.5"
                stroke-linejoin="round" stroke-linecap="round"/>
      <!-- G inner shelf -->
      <line x1="36" y1="55" x2="44" y2="60"
            stroke="#FFAD28" stroke-width="2.5" stroke-linecap="round"/>
    </svg>
    """

    # 1. Google Fonts — separate call, no f-string needed.
    st.markdown(
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
        '<link href="https://fonts.googleapis.com/css2?family=Funnel+Sans:wght@300..800&display=swap"'
        ' rel="stylesheet">',
        unsafe_allow_html=True,
    )

    # 2. CSS — build as plain string with .format() so curly braces in CSS
    #    rules don't need escaping and can't accidentally be treated as
    #    f-string interpolation targets.
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
div[data-testid="stSidebarNav"] a:hover {
    background-color: rgba(255,173,40,0.12) !important;
    border-radius: 6px;
}
div[data-testid="stSidebarNav"] a[aria-current="page"] {
    background-color: rgba(255,173,40,0.18) !important;
    border-left: 3px solid #FFAD28 !important;
    border-radius: 0 6px 6px 0;
}
div[data-testid="stMetric"] {
    background-color: CARD_BG_VAL;
    border: 1px solid BORDER_VAL;
    border-radius: 8px;
    padding: 12px;
}
#kt-brand-header {
    padding: 20px 16px 16px 16px;
    border-bottom: 1px solid rgba(255,255,255,0.10);
    margin-bottom: 8px;
}
#kt-brand-header .kt-logo-row {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 6px;
}
#kt-brand-header .kt-product-name {
    font-family: 'Funnel Sans', sans-serif;
    font-weight: 700;
    font-size: 1.05rem;
    color: #FFFFFF;
    letter-spacing: -0.01em;
    line-height: 1.2;
}
#kt-brand-header .kt-full-form {
    font-family: 'Funnel Sans', sans-serif;
    font-weight: 300;
    font-size: 0.68rem;
    color: rgba(255,255,255,0.55);
    letter-spacing: 0.02em;
    line-height: 1.4;
    padding-left: 54px;
}
</style>
""".replace("PAGE_BG_VAL", PAGE_BG).replace("INK_VAL", INK).replace(
        "NAV_BG_VAL", NAV_BG
    ).replace("CARD_BG_VAL", CARD_BG).replace("BORDER_VAL", BORDER)

    st.markdown(css, unsafe_allow_html=True)

    # 3. Brand header — sidebar only, once per render pass.
    if not already_injected:
        st.sidebar.markdown(
            "<div id='kt-brand-header'>"
            "<div class='kt-logo-row'>"
            + cube_svg
            + "<span class='kt-product-name'>KT Assist</span>"
            "</div>"
            "<div class='kt-full-form'>"
            "Knowledge Transition &amp; Assurance Platform"
            "</div>"
            "</div>",
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
