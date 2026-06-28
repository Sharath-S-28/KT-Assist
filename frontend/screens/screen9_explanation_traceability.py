"""
frontend/screens/screen9_explanation_traceability.py — Screen 9:
Explanation & Traceability (Phase 11 / Session 34). Confirmed via
services/traceability_service.py's "Chunk 8 Screen 9" reference and
schemas/explanation.py's "receiver_id... to match Screen 9 language"
comment.

[FROZEN] content: the L1/L2/L3 explanation (schemas.explanation.
ExplanationResponse -- headline, decision sentence, reason/missing-
evidence/strengths sentences, and the Claude-or-template narrative),
the seven-level traceability tree (client.get_trace), and per-
competency remediation recommendations (client.get_recommendations).

Screen 9 takes a receiver, not a raw receiver_readiness_id, the same way
Screen 8 does -- client.get_readiness_dashboard(receiver.id) is called
first purely to resolve receiver_readiness_id (Session 34's addition to
ReadinessDashboard), then every explanation endpoint is called with that
id. This avoids ever asking a user to type or paste a UUID.

The trace tree is rendered as a single top-level expander containing
indented markdown, rather than a graph visualization or nested
expanders -- frontend/components has no tree widget, Screen 4 (Graph
Explorer) already owns this app's one graph-rendering surface
(get_graph_html via pyvis), and Streamlit's st.expander does not support
nesting (StreamlitAPIException: "Expanders may not be nested inside
other expanders" -- discovered via Session 34's end-to-end AppTest
verification, not assumed). Only the root node opens an expander; every
deeper level renders as indented bold/plain markdown instead of further
expanders.
"""

import streamlit as st

from frontend.api_client import ApiClient, ApiError, TraceNode
from frontend.theme import inject_global_css


def _render_trace_node(node: TraceNode, depth: int = 0) -> None:
    label = node.label if node.value is None else f"{node.label}: {node.value}"
    indent = "&nbsp;&nbsp;&nbsp;&nbsp;" * depth
    if not node.children:
        st.markdown(f"{indent}- {label}", unsafe_allow_html=True)
        return
    if depth == 0:
        with st.expander(f"{label} ({len(node.children)})", expanded=True):
            for child in node.children:
                _render_trace_node(child, depth + 1)
        return
    st.markdown(f"{indent}- **{label}** ({len(node.children)})", unsafe_allow_html=True)
    for child in node.children:
        _render_trace_node(child, depth + 1)


def render(client: ApiClient) -> None:
    inject_global_css()
    st.title("Explanation & Traceability")

    participants = client.list_participants()
    receivers = [p for p in participants if p.participant_type == "Receiver"]
    if not receivers:
        st.info("No receivers exist yet. Add one on the Participant Management screen.")
        return

    selected_name = st.selectbox("Receiver", options=[p.name for p in receivers])
    receiver = next(p for p in receivers if p.name == selected_name)

    try:
        dashboard = client.get_readiness_dashboard(receiver.id)
    except ApiError as exc:
        if exc.status_code == 404:
            st.caption("No readiness assessment has run for this receiver yet.")
            return
        raise

    readiness_id = dashboard.receiver_readiness_id
    explanation = client.get_explanation(readiness_id)

    st.subheader(explanation.headline)
    st.write(explanation.decision_sentence)

    if explanation.reason_sentences:
        st.write("**Reasons**")
        for sentence in explanation.reason_sentences:
            st.write(f"- {sentence}")

    if explanation.missing_evidence_sentences:
        st.write("**Missing Evidence**")
        for sentence in explanation.missing_evidence_sentences:
            st.write(f"- {sentence}")

    if explanation.strengths_sentences:
        st.write("**Strengths**")
        for sentence in explanation.strengths_sentences:
            st.write(f"- {sentence}")

    st.caption(f"Narrative source: {explanation.narrative_source}")
    st.write(explanation.narrative)

    st.subheader("Recommendations")
    recommendations = client.get_recommendations(readiness_id)
    if not recommendations:
        st.caption("No outstanding remediation recommendations.")
    else:
        for rec in recommendations:
            with st.container(border=True):
                st.write(f"**{rec.competency_name}** — score {rec.score:.0f}")
                for action in rec.actions:
                    st.write(f"- {action}")

    st.subheader("Traceability Tree")
    trace = client.get_trace(readiness_id)
    _render_trace_node(trace)
