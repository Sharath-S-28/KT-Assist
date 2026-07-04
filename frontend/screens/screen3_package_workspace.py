"""
frontend/screens/screen3_package_workspace.py — Screen 3: Knowledge
Package Workspace (Phase 11 / Session 33 + assessment workflow addition).

[FROZEN] read content: knowledge assets list, knowledge summary
(object count, relationship count, confidence, coverage).

Write paths added (same session as assessment backend endpoints):
  - Create Knowledge Package (name + program selection).
  - Upload Document (st.file_uploader -> client.upload_asset) -- the
    one Streamlit file-upload surface in the entire app. Displays
    extraction summary + coverage + package_type inline after upload so
    the KT Manager sees immediate feedback without navigating away.
  - Generate Assessment (client.generate_assessment) -- triggers the
    scenario-generation pipeline for the selected package and shows
    a scenario count summary. Placed here rather than on Screen 7
    because it is a KT Manager action on a package, not a receiver
    action, exactly like uploading a document.
  - Score Receiver (client.score_readiness) -- available once all
    scenario responses exist; also on this screen for the same reason.

The scenario-answering surface (list scenarios, type responses, submit)
lives on Screen 7 (Participant Management) under a "Receiver Assessment"
tab, since it is a receiver-facing action scoped to a participant, not
a package-management action.
"""

import streamlit as st

from frontend.api_client import ApiClient, ApiError
from frontend.theme import inject_global_css


def render(client: ApiClient) -> None:
    inject_global_css()
    st.title("Knowledge Package Workspace")

    # ── Create Package ──────────────────────────────────────────────────────
    with st.expander("➕ Create New Knowledge Package", expanded=False):
        programs = client.list_programs()
        if not programs:
            st.caption("No programs exist yet — create one on the Program Dashboard first.")
        else:
            with st.form("create_package_form"):
                pkg_program = st.selectbox(
                    "Program", options=[p.name for p in programs], key="pkg_prog_select"
                )
                pkg_name = st.text_input("Package Name")
                pkg_submitted = st.form_submit_button("Create Package")
                if pkg_submitted:
                    if not pkg_name.strip():
                        st.error("Package name is required.")
                    else:
                        program = next(p for p in programs if p.name == pkg_program)
                        try:
                            client.create_package(program_id=program.id, name=pkg_name.strip())
                        except ApiError as exc:
                            st.error(f"Could not create package: {exc.message}")
                        else:
                            st.success(f"Created package '{pkg_name}'.")
                            st.rerun()

    # ── Package selector ────────────────────────────────────────────────────
    packages = client.list_packages()
    if not packages:
        st.info("No knowledge packages exist yet. Use '➕ Create New Knowledge Package' above.")
        return

    selected_name = st.selectbox("Package", options=[p.name for p in packages])
    package = next(p for p in packages if p.name == selected_name)

    if package.description:
        st.caption(package.description)

    # ── Upload Document ─────────────────────────────────────────────────────
    st.subheader("Upload Source Document")
    uploaded = st.file_uploader(
        "Transcript, runbook, SOP (txt, pdf, docx, pptx)",
        type=["txt", "pdf", "docx", "pptx"],
        key=f"upload-{package.id}",
    )
    if uploaded is not None:
        if st.button("Upload & Extract", key=f"upload-btn-{package.id}"):
            with st.spinner("Extracting knowledge objects and computing coverage…"):
                try:
                    result = client.upload_asset(
                        package_id=package.id,
                        filename=uploaded.name,
                        content=uploaded.getvalue(),
                    )
                except ApiError as exc:
                    st.error(f"Upload failed: {exc.message}")
                    result = None

            if result is not None:
                st.success(
                    f"Extracted **{result.object_count}** knowledge objects "
                    f"| Package type: **{result.package_type}** "
                    f"| Coverage: **{result.coverage_score * 100:.0f}%** "
                    f"({'✅ Sufficient' if result.is_sufficient else '⚠️ Gaps detected'})"
                )
                if result.objects:
                    by_type: dict[str, int] = {}
                    for obj in result.objects:
                        by_type[obj.object_type] = by_type.get(obj.object_type, 0) + 1
                    st.caption(
                        "  ·  ".join(f"{t}: {n}" for t, n in sorted(by_type.items()))
                    )
                st.rerun()

    # ── Knowledge Assets ────────────────────────────────────────────────────
    st.subheader("Knowledge Assets")
    assets = client.list_assets(package.id)
    if assets:
        st.dataframe(
            [
                {
                    "Filename": a.filename,
                    "Type": a.file_type,
                    "Extraction Status": a.extraction_status,
                }
                for a in assets
            ],
            use_container_width=True,
        )
    else:
        st.caption("No source documents uploaded yet.")

    # ── Knowledge Summary ───────────────────────────────────────────────────
    st.subheader("Knowledge Summary")
    try:
        graph = client.get_graph(package.id)
    except ApiError as exc:
        if exc.status_code == 404:
            st.caption("No knowledge graph extracted yet for this package.")
            graph = None
        else:
            raise

    if graph is not None:
        mean_confidence = (
            sum(node.confidence for node in graph.nodes) / len(graph.nodes)
            if graph.nodes
            else None
        )
        cols = st.columns(4)
        with cols[0]:
            st.metric("Knowledge Objects", len(graph.nodes))
        with cols[1]:
            st.metric("Relationships", len(graph.relationships))
        with cols[2]:
            st.metric(
                "Mean Confidence",
                f"{mean_confidence:.0%}" if mean_confidence is not None else "—",
            )
        with cols[3]:
            coverage = package.latest_coverage_score
            st.metric(
                "Coverage",
                f"{coverage * 100:.0f}%" if coverage is not None else "—",
            )

    # ── Generate Assessment ─────────────────────────────────────────────────
    st.divider()
    st.subheader("Assessment Pipeline")

    if not assets:
        st.caption("Upload a document first before generating an assessment.")
    else:
        col_gen, col_score = st.columns(2)

        with col_gen:
            if st.button("Generate Assessment Scenarios", key=f"gen-{package.id}"):
                with st.spinner("Generating and validating scenarios…"):
                    try:
                        result = client.generate_assessment(package.id)
                    except ApiError as exc:
                        st.error(f"Generation failed: {exc.message}")
                        result = None
                if result is not None:
                    st.success(
                        f"Generated **{result.scenario_count}** scenarios "
                        f"| Status: {result.status} "
                        f"| Pillar complete: {'Yes' if result.is_pillar_complete else 'No'}"
                    )

        with col_score:
            participants = client.list_participants()
            receivers = [p for p in participants if p.participant_type == "Receiver"]
            if not receivers:
                st.caption("No receivers yet — add one on Participant Management.")
            else:
                receiver_name = st.selectbox(
                    "Score receiver",
                    options=[p.name for p in receivers],
                    key=f"score-receiver-{package.id}",
                )
                role_tier = st.selectbox(
                    "Role tier",
                    options=["Primary", "Secondary", "Oversight"],
                    key=f"score-tier-{package.id}",
                )
                receiver = next(p for p in receivers if p.name == receiver_name)
                if st.button("Score Readiness", key=f"score-{package.id}"):
                    with st.spinner("Running evidence detection and scoring…"):
                        try:
                            score = client.score_readiness(
                                package_id=package.id,
                                participant_id=receiver.id,
                                role_tier=role_tier,
                            )
                        except ApiError as exc:
                            st.error(f"Scoring failed: {exc.message}")
                            score = None
                    if score is not None:
                        decision_color_map = {
                            "Ready": "#3D6B4F",
                            "Conditionally Ready": "#FFAD28",
                            "Not Ready": "#FF4F59",
                        }
                        color = decision_color_map.get(score.decision, "#444744")
                        st.markdown(
                            f'<div style="background:{color};color:#fff;padding:12px 16px;'
                            f'border-radius:8px;font-weight:700;text-align:center;">'
                            f'{score.decision} — OIS {score.ois_score:.1f}</div>',
                            unsafe_allow_html=True,
                        )
                        st.write("")
                        pillar_cols = st.columns(4)
                        for i, p in enumerate(sorted(score.pillar_scores, key=lambda x: x.pillar)):
                            with pillar_cols[i % 4]:
                                st.metric(p.pillar, f"{p.score:.0f}")
