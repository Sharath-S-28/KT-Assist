"""
config/ui.py — UI constants for KT Assist.

Currently: the frozen Genpact colour system (Appendix C).
Kept in its own module because colour changes are a design decision
entirely independent of scoring thresholds or domain vocabulary.
"""

# Fixed semantic colour mapping (Appendix C).
COLORS = {
    "primary_text":       "#161916",
    "nav_secondary":      "#282A27",
    "borders":            "#444744",
    "placeholder":        "#6D706B",
    "page_background":    "#FFFFFF",
    "card_background":    "#FFFAF4",
    "callout_background": "#FFF2DF",
    "error_not_ready":    "#FF4F59",
    "warning_conditional": "#FFAD28",
    "success_ready":      "#3D6B4F",
}
