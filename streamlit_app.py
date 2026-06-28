"""
streamlit_app.py — Phase 11 / Session 33 Streamlit entry point.

Drives navigation explicitly via st.navigation()/st.Page() rather than
Streamlit's auto-discovered sibling `pages/` directory, per the
reconciliation already documented in frontend/__init__.py: a flat,
alphabetically-ordered `pages/` sidebar cannot express the locked
8-concept nav grouping (e.g. Screen 6 must sit under the same
"Knowledge Packages" group as Screens 3-5, not get its own top-level
slot).

Nav grouping, final ruling as of Session 34 (Screens 1-10 complete).
frontend/__init__.py's "locked 8-concept nav grouping" phrase is itself
a casualty of the same lost-spec-text problem documented in Screens 7
and 10's docstrings -- no enumeration of the 8 concepts survived
compaction. Rather than guess at 8 arbitrary groups, this ruling groups
the 10 screens by the entity they're scoped to, the same scoping
already visible in each screen's own first selectbox (Program vs.
Package vs. Receiver):
  - "Overview"     -> Screen 1 (program-independent, top-level)
  - "Programs"     -> Screen 2 (program-scoped dashboard) and Screen 10
    (KT Assurance Report -- also program-scoped: it rolls up a single
    program's packages/receivers into one report, the natural "closing"
    counterpart to Screen 2's program dashboard).
  - "Knowledge Packages" -> Screens 3, 4, 5, 6 (all package-scoped --
    Package Workspace, Graph Explorer, Validation Center, Gap
    Resolution Workspace).
  - "Receivers"    -> Screens 7, 8, 9 (all receiver-scoped -- Participant
    & Receiver Role Management creates the receiver/role data the other
    two consume; Readiness Scorecard and Explanation & Traceability are
    both per-receiver views keyed off the same receiver selector).

[PROPOSAL] demo role selector: deferred rather than built here. Screens
1-6 remain provider/PM-facing. Screens 7-9 (Session 34) are the first
receiver-scoped screens, but they are still operated by a PM/provider
configuring or reviewing a receiver's data, not by the receiver
themselves logging in as that role -- there is no auth/session concept
of "the current receiver" anywhere in the backend (Participant rows are
looked up by id, not by a logged-in identity). A "view as Receiver"
selector would have nothing to gate, since every screen already shows
every receiver's data to whoever opens it. Deferred indefinitely unless
a future session adds receiver-scoped auth.

One ApiClient is built once per Streamlit session (st.session_state)
and shared by every screen, per frontend/api_client.py's get_client().
"""

import streamlit as st

from frontend.api_client import get_client
from frontend.screens import (
    screen1_executive_dashboard,
    screen2_program_dashboard,
    screen3_package_workspace,
    screen4_graph_explorer,
    screen5_validation_center,
    screen6_gap_resolution_workspace,
    screen7_participant_management,
    screen8_readiness_scorecard,
    screen9_explanation_traceability,
    screen10_kt_assurance_report,
)


def _screen1():
    screen1_executive_dashboard.render(get_client())


def _screen2():
    screen2_program_dashboard.render(get_client())


def _screen3():
    screen3_package_workspace.render(get_client())


def _screen4():
    screen4_graph_explorer.render(get_client())


def _screen5():
    screen5_validation_center.render(get_client())


def _screen6():
    screen6_gap_resolution_workspace.render(get_client())


def _screen7():
    screen7_participant_management.render(get_client())


def _screen8():
    screen8_readiness_scorecard.render(get_client())


def _screen9():
    screen9_explanation_traceability.render(get_client())


def _screen10():
    screen10_kt_assurance_report.render(get_client())


def main() -> None:
    st.set_page_config(page_title="KT Assist", layout="wide")

    overview = st.Page(_screen1, title="Executive Dashboard", url_path="executive-dashboard", default=True)
    programs = st.Page(_screen2, title="Program Dashboard", url_path="program-dashboard")
    packages = st.Page(_screen3, title="Package Workspace", url_path="package-workspace")
    graph = st.Page(_screen4, title="Graph Explorer", url_path="graph-explorer")
    validation = st.Page(_screen5, title="Validation Center", url_path="validation-center")
    gap_resolution = st.Page(_screen6, title="Gap Resolution Workspace", url_path="gap-resolution-workspace")
    participants = st.Page(_screen7, title="Participant & Receiver Role Management", url_path="participant-management")
    scorecard = st.Page(_screen8, title="Readiness Scorecard", url_path="readiness-scorecard")
    explanation = st.Page(_screen9, title="Explanation & Traceability", url_path="explanation-traceability")
    assurance_report = st.Page(_screen10, title="KT Assurance Report", url_path="assurance-report")

    nav = st.navigation(
        {
            "Overview": [overview],
            "Programs": [programs, assurance_report],
            "Knowledge Packages": [packages, graph, validation, gap_resolution],
            "Receivers": [participants, scorecard, explanation],
        }
    )
    nav.run()


if __name__ == "__main__":
    main()
