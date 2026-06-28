"""
frontend/screens/screen2_program_dashboard.py — Screen 2: KT Program
Dashboard (Phase 11 / Session 33). [FROZEN] content: KT info,
participants, packages, status, coverage, readiness; a lifecycle tracker
(Draft -> Capture -> Validate -> Enrich -> Assess -> Ready); package
cards (coverage, open gaps, status, readiness).

Built on client.get_program / client.list_packages / client.list_participants
(Phase 2/5/8). No package-level open-gap count or readiness endpoint
exists yet (that's Screen 5/6/8's territory in S33/S34) -- this screen
shows "Status" from KnowledgePackageRead.latest_coverage_score and
package_type/complexity rather than inventing an open-gaps figure no
backend endpoint has computed.

[PROPOSAL]: a program selectbox drives this screen rather than a URL
param -- Streamlit's st.navigation() pages don't take query args by
default, and the spec doesn't pin a navigation mechanism finer than
"screen", so program selection is in-page session state.
"""

import streamlit as st

from frontend.api_client import ApiClient
from frontend.components import lifecycle_tracker, package_card
from frontend.theme import inject_global_css


def render(client: ApiClient) -> None:
    inject_global_css()
    st.title("KT Program Dashboard")

    programs = client.list_programs()
    if not programs:
        st.info("No KT programs exist yet. Create one to get started.")
        return

    selected_name = st.selectbox("Program", options=[p.name for p in programs])
    program = next(p for p in programs if p.name == selected_name)

    st.subheader(program.name)
    if program.description:
        st.caption(program.description)

    info_cols = st.columns(2)
    with info_cols[0]:
        st.write(f"**Lifecycle State:** {program.lifecycle_state}")
    with info_cols[1]:
        st.write(f"**Completion Status:** {program.completion_status}")

    lifecycle_tracker(program.lifecycle_state)

    st.divider()

    participants = client.list_participants(program_id=program.id)
    st.subheader(f"Participants ({len(participants)})")
    if participants:
        st.dataframe(
            [{"Name": p.name, "Type": p.participant_type, "Email": p.email or "—"} for p in participants],
            use_container_width=True,
        )
    else:
        st.caption("No participants added yet.")

    packages = client.list_packages(program_id=program.id)
    st.subheader(f"Knowledge Packages ({len(packages)})")
    if packages:
        for package in packages:
            package_card(
                name=package.name,
                coverage=package.latest_coverage_score,
                open_gaps=0,  # no open-gaps-by-package endpoint exists yet; see module docstring
                status=package.package_type or "Type not set",
                readiness=None,  # readiness is receiver-scoped (Screen 8), not package-scoped
            )
    else:
        st.caption("No knowledge packages created yet.")
