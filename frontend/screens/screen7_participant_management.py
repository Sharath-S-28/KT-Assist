"""
frontend/screens/screen7_participant_management.py — Screen 7: Participant
& Receiver Role Management (Phase 11 / Session 34).

Reconstruction note: the original Phase 11 spec text for Screens 7 and 10
was lost to context compaction and never persisted to disk (see Session
34's other screens' docstrings for the same caveat). Screen 7's content
is ruled here from codebase evidence rather than guessed: every other
backend capability already has a Session 33/34 screen consuming it
EXCEPT services/routers/participants.py's four endpoints --
list_participants, create_participant, get_participant,
assign_receiver_role -- all already wired into frontend/api_client.py
since Session 33, but never called by any screen built so far. That is
the same "client method exists, no screen consumes it" pattern that
flagged Screens 1-6's content; ruling Screen 7 = Participant & Receiver
Role Management closes that gap rather than inventing unrelated content.

This also resolves a real workflow dependency: Screen 8 (Readiness
Scorecard) and the future receiver-facing screens all key off an
existing Participant id with a receiver role already assigned to a
package -- something had to create that data through the UI, and no
other screen does.
"""

import streamlit as st

from frontend.api_client import ApiClient, ApiError
from frontend.theme import inject_global_css

_PARTICIPANT_TYPES = ["Provider", "Receiver", "KT Manager", "SME", "Leadership"]  # schemas.participant.ParticipantCreate.participant_type
_ROLE_TIERS = ["Primary", "Secondary", "Oversight"]


def render(client: ApiClient) -> None:
    inject_global_css()
    st.title("Participant & Receiver Role Management")

    programs = client.list_programs()
    if not programs:
        st.info("No programs exist yet.")
        return

    program_name = st.selectbox("Program", options=[p.name for p in programs])
    program = next(p for p in programs if p.name == program_name)

    st.subheader("Participants")
    participants = client.list_participants(program_id=program.id)
    if participants:
        st.table(
            [{"Name": p.name, "Type": p.participant_type, "Email": p.email or "—"} for p in participants]
        )
    else:
        st.caption("No participants in this program yet.")

    with st.form("create_participant_form"):
        st.write("Add Participant")
        name = st.text_input("Name")
        participant_type = st.selectbox("Type", options=_PARTICIPANT_TYPES)
        email = st.text_input("Email (optional)")
        submitted = st.form_submit_button("Create Participant")
        if submitted:
            if not name.strip():
                st.error("Name is required.")
            else:
                try:
                    client.create_participant(
                        program_id=program.id,
                        name=name,
                        participant_type=participant_type,
                        email=email or None,
                    )
                except ApiError as exc:
                    st.error(f"Could not create participant: {exc.message}")
                else:
                    st.success(f"Created participant {name}.")
                    st.rerun()

    st.subheader("Assign Receiver Role")
    packages = client.list_packages(program_id=program.id)
    if not participants or not packages:
        st.caption("Need at least one participant and one knowledge package to assign a role.")
        return

    with st.form("assign_role_form"):
        participant_name = st.selectbox("Participant", options=[p.name for p in participants])
        package_name = st.selectbox("Knowledge Package", options=[pk.name for pk in packages])
        role_tier = st.selectbox("Role Tier", options=_ROLE_TIERS)
        submitted = st.form_submit_button("Assign Role")
        if submitted:
            participant = next(p for p in participants if p.name == participant_name)
            package = next(pk for pk in packages if pk.name == package_name)
            try:
                assignment = client.assign_receiver_role(
                    participant_id=participant.id, package_id=package.id, role_tier=role_tier
                )
            except ApiError as exc:
                st.error(f"Could not assign role: {exc.message}")
            else:
                st.success(
                    f"Assigned {role_tier} role to {participant_name} on {package_name} "
                    f"(effective OIS threshold: {assignment.effective_ois_threshold})."
                )
