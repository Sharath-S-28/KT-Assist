"""
frontend/screens/screen7_participant_management.py — Screen 7: Participant
& Receiver Role Management (Phase 11 / Session 34 + receiver assessment).

Three tabs:
  1. Participants — list + create participant, assign receiver role.
     (original Session 33/34 content, unchanged.)
  2. Receiver Assessment — list scenarios for a package, collect the
     receiver's free-text responses one by one, submit each as they go.
     This is the only receiver-facing write surface in the app; it lives
     here rather than Screen 3 because it is scoped to a participant
     (receiver), not a package management action.

Scoring is triggered from Screen 3 (Package Workspace) once all
responses have been submitted, keeping the two concerns separated:
Screen 3 = KT Manager actions (upload, generate, score);
Screen 7 = receiver actions (answer scenarios).
"""

import streamlit as st

from frontend.api_client import ApiClient, ApiError
from frontend.theme import inject_global_css

_PARTICIPANT_TYPES = ["Provider", "Receiver", "KT Manager", "SME", "Leadership"]
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

    tab_participants, tab_assessment = st.tabs(
        ["👥 Participants & Roles", "📝 Receiver Assessment"]
    )

    # ── Tab 1: Participants & Roles ─────────────────────────────────────────
    with tab_participants:
        participants = client.list_participants(program_id=program.id)

        st.subheader("Participants")
        if participants:
            st.table(
                [
                    {"Name": p.name, "Type": p.participant_type, "Email": p.email or "—"}
                    for p in participants
                ]
            )
        else:
            st.caption("No participants in this program yet.")

        with st.form("create_participant_form"):
            st.write("**Add Participant**")
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
            st.caption("Need at least one participant and one knowledge package.")
        else:
            with st.form("assign_role_form"):
                participant_name = st.selectbox(
                    "Participant", options=[p.name for p in participants]
                )
                package_name = st.selectbox(
                    "Knowledge Package", options=[pk.name for pk in packages]
                )
                role_tier = st.selectbox("Role Tier", options=_ROLE_TIERS)
                submitted = st.form_submit_button("Assign Role")
                if submitted:
                    participant = next(p for p in participants if p.name == participant_name)
                    package = next(pk for pk in packages if pk.name == package_name)
                    try:
                        assignment = client.assign_receiver_role(
                            participant_id=participant.id,
                            package_id=package.id,
                            role_tier=role_tier,
                        )
                    except ApiError as exc:
                        st.error(f"Could not assign role: {exc.message}")
                    else:
                        st.success(
                            f"Assigned {role_tier} role to {participant_name} on "
                            f"{package_name} (effective OIS threshold: "
                            f"{assignment.effective_ois_threshold})."
                        )

    # ── Tab 2: Receiver Assessment ──────────────────────────────────────────
    with tab_assessment:
        st.subheader("Receiver Assessment")
        st.caption(
            "Select a receiver and package, then answer each scenario below. "
            "Submit each response individually. Once all responses are in, "
            "trigger scoring from the Package Workspace screen."
        )

        participants = client.list_participants(program_id=program.id)
        packages = client.list_packages(program_id=program.id)

        receivers = [p for p in participants if p.participant_type == "Receiver"]
        if not receivers:
            st.info("No receivers in this program yet. Add one in the Participants tab.")
            return
        if not packages:
            st.info("No knowledge packages in this program yet.")
            return

        receiver_name = st.selectbox(
            "Receiver", options=[p.name for p in receivers], key="assess_receiver"
        )
        receiver = next(p for p in receivers if p.name == receiver_name)

        package_name = st.selectbox(
            "Package", options=[pk.name for pk in packages], key="assess_package"
        )
        package = next(pk for pk in packages if pk.name == package_name)

        # Load scenarios for this package
        try:
            scenarios = client.list_scenarios(package.id)
        except ApiError as exc:
            if exc.status_code == 404:
                st.info(
                    "No assessment scenarios generated yet for this package. "
                    "Go to Package Workspace and click 'Generate Assessment Scenarios' first."
                )
                return
            raise

        if not scenarios:
            st.info("No scenarios available. Generate assessment first on Package Workspace.")
            return

        st.write(f"**{len(scenarios)} scenarios** to answer as {receiver_name}:")
        st.divider()

        submitted_count = 0
        for i, scenario in enumerate(scenarios):
            with st.container(border=True):
                st.markdown(
                    f"**Scenario {i + 1} of {len(scenarios)}** "
                    f"· {scenario.category} · {scenario.difficulty}"
                )
                st.write(f"**Situation:** {scenario.situation}")
                if scenario.decision_point:
                    st.write(f"**Question:** {scenario.decision_point}")

                response_key = f"response-{scenario.id}-{receiver.id}"
                response_text = st.text_area(
                    "Your answer",
                    key=response_key,
                    height=100,
                    placeholder="Describe what you would do, step by step…",
                )

                btn_key = f"submit-{scenario.id}-{receiver.id}"
                if st.button("Submit Response", key=btn_key, disabled=not (response_text or "").strip()):
                    try:
                        client.submit_scenario_response(
                            scenario_id=scenario.id,
                            participant_id=receiver.id,
                            response_text=response_text.strip(),
                        )
                    except ApiError as exc:
                        st.error(f"Submission failed: {exc.message}")
                    else:
                        st.success("Response submitted.")
                        submitted_count += 1

        if submitted_count > 0:
            st.rerun()
