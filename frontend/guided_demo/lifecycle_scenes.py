"""
frontend/guided_demo/lifecycle_scenes.py — detailed Knowledge Lifecycle
Experience scenes (UI Phase 2), integrated into the Guided Demo Case
Shell.

Each render_* function is a read-mostly presentation layer over real
backend outputs (frontend.api_client.ApiClient) -- KCS/KQS/TC/AC/RC/
OS/EV, Findings/Knowledge Gaps, closure-round history, and Transition
Risks all come from the real hierarchical lifecycle
(services/coverage/*, services/agents/kase.py's KAR builder) via the
demo orchestrator. Nothing here recomputes a score or fabricates an
intermediate metric; every mutating action (ingest/validate/advance
enrichment) is an explicit button press calling the real, already-
tested demo API, never triggered on a passive rerender.
"""

import streamlit as st

from frontend.api_client import ApiClient, ApiError
from frontend.guided_demo.presentation_labels import attribute_state_label, rule_family_label
from frontend.theme import BORDER, CARD_BG, MUTED, badge_html, decision_color

_GATE_OK = "#3D6B4F"
_GATE_FAIL = "#FF4F59"


def _gate_badge(passed: bool, label: str) -> str:
    color = _GATE_OK if passed else _GATE_FAIL
    return badge_html(f"{label}: {'Pass' if passed else 'Not Yet'}", color)


def _dimension_row(kar: dict) -> None:
    cols = st.columns(5)
    labels = [("Type Completeness", "tc"), ("Attribute Completeness", "ac"), ("Relationship Completeness", "rc"),
              ("Operational Sufficiency", "os"), ("Evidence Validation", "ev")]
    for col, (label, key) in zip(cols, labels):
        with col:
            value = kar.get(key)
            st.metric(label, f"{value * 100:.0f}%" if value is not None else "—")


# ---------------------------------------------------------------------------
# 1. Knowledge Intake
# ---------------------------------------------------------------------------

def render_knowledge_intake(client: ApiClient, summary: dict) -> None:
    st.subheader("Knowledge Intake")
    st.caption("The transition begins from real source knowledge, not a prebuilt dashboard.")

    stage = summary.get("stage", "START")
    cols = st.columns(4)
    with cols[0]:
        st.metric("Source Document", "KT Transcript")
    with cols[1]:
        st.metric("Knowledge Provider", "Ravi")
    with cols[2]:
        st.metric("Receiver Group", f"{len(summary.get('receivers', {})) or 3} pinned receivers")
    with cols[3]:
        st.metric("Ingestion Status", "Complete" if stage != "START" else "Not Started")

    st.markdown(
        f"**Backend journey stage:** `{stage}` &nbsp;&nbsp; **Profile:** "
        f"`{summary.get('profile_id') or '—'}` &nbsp;&nbsp; "
        f"**Last checkpoint:** graph version {summary.get('graph_version_number') or '—'}",
        unsafe_allow_html=True,
    )
    st.markdown(
        badge_html("Deterministic validated replay — no external model call required", MUTED),
        unsafe_allow_html=True,
    )

    if stage == "START":
        if st.button("Begin Knowledge Intake", type="primary", key="intake_begin"):
            try:
                client.ingest_demo_hierarchical()
            except ApiError as exc:
                st.error(f"Could not begin knowledge intake: {exc.message}")
                return
            st.rerun()
    else:
        st.success("Knowledge intake complete — the real KAI extraction cache was used (no live model call).")


# ---------------------------------------------------------------------------
# 2. Knowledge Discovery
# ---------------------------------------------------------------------------

def render_knowledge_discovery(client: ApiClient, summary: dict) -> None:
    st.subheader("Knowledge Discovery")
    st.caption("What the system discovered from the source knowledge.")

    if summary.get("stage") == "START":
        st.info("Complete Knowledge Intake first to discover the knowledge graph.")
        return

    discovery = client.get_demo_discovery_summary()
    if not discovery.get("available"):
        st.info("No knowledge graph is available yet.")
        return

    cols = st.columns(4)
    with cols[0]:
        st.metric("Knowledge Objects", discovery["node_count"])
    with cols[1]:
        st.metric("Relationships", discovery["relationship_count"])
    with cols[2]:
        st.metric("Object Types", len(discovery["object_type_distribution"]))
    with cols[3]:
        st.metric("Attributes Captured", discovery["attributes_captured"])

    st.write("")
    chart_col1, chart_col2 = st.columns(2)
    with chart_col1:
        st.markdown("**Object-Type Distribution**")
        st.bar_chart(discovery["object_type_distribution"])
    with chart_col2:
        st.markdown("**Attribute-State Distribution**")
        readable_states = {
            attribute_state_label(k): v for k, v in discovery["attribute_state_distribution"].items()
        }
        st.bar_chart(readable_states)

    st.markdown("**Knowledge Landscape**")
    st.dataframe(
        [{"Object Type": t, "Count": c} for t, c in discovery["object_type_distribution"].items()],
        use_container_width=True, hide_index=True,
    )

    if discovery["examples"]:
        st.markdown("**Grounding Examples**")
        for object_type, example in discovery["examples"].items():
            st.markdown(
                f"""
                <div style="background-color:{CARD_BG};border:1px solid {BORDER};
                border-radius:8px;padding:12px 16px;margin-bottom:8px;">
                    <div style="font-weight:700;">{object_type}: {example['name']}
                        &nbsp;{badge_html(example['criticality'], MUTED)}</div>
                    <div style="margin-top:4px;color:{MUTED};">{example['description']}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


# ---------------------------------------------------------------------------
# 3. Knowledge Assurance
# ---------------------------------------------------------------------------

def render_knowledge_assurance(client: ApiClient, summary: dict) -> None:
    st.subheader("Knowledge Assurance")
    st.caption("Knowledge was captured, but captured knowledge is not automatically transition-ready.")

    if summary.get("stage") == "START":
        st.info("Complete Knowledge Intake and Discovery first.")
        return

    snapshot = client.get_demo_assurance_snapshot()
    current = snapshot.get("current")
    if current is None:
        st.info("Run Knowledge Discovery first to compute the initial assurance position.")
        return

    cols = st.columns(2)
    with cols[0]:
        st.metric("Knowledge Completeness Score (KCS)", f"{current['kcs'] * 100:.0f}%" if current["kcs"] is not None else "—")
    with cols[1]:
        st.metric("Knowledge Quality Score (KQS)", f"{current['kqs'] * 100:.0f}%" if current["kqs"] is not None else "—")

    st.write("")
    st.markdown("**Dimension Breakdown**")
    _dimension_row(current)

    st.write("")
    st.markdown(
        _gate_badge(current["sufficiency_gate_passed"], "Sufficiency Gate") + "&nbsp;&nbsp;" +
        (_gate_badge(current["quality_gate_passed"], "Quality Gate") if current["quality_gate_applicable"] else ""),
        unsafe_allow_html=True,
    )
    st.caption(
        "Sufficiency measures how much required knowledge exists. Quality measures how well-validated it is. "
        "Either gate failing blocks transition readiness regardless of the other."
    )

    gaps = client.get_demo_knowledge_gaps()
    st.write("")
    gap_cols = st.columns(3)
    with gap_cols[0]:
        st.metric("Findings", gaps.get("findings_count", 0))
    with gap_cols[1]:
        st.metric("Knowledge Gaps", gaps.get("gaps_count", 0))
    with gap_cols[2]:
        critical = sum(1 for g in gaps.get("gaps", []) if g["blocking_readiness_gate"])
        st.metric("Critical / Blocking", critical)

    top_gaps = gaps.get("gaps", [])[:5]
    if top_gaps:
        st.markdown("**Top Prioritized Gaps**")
        st.dataframe(
            [
                {
                    "Object": g["object_name"],
                    "Theme": rule_family_label(g["rule_family"]),
                    "Criticality": g["criticality"],
                    "Risk": g["risk_level"],
                    "Blocking": "Yes" if g["blocking_readiness_gate"] else "No",
                }
                for g in top_gaps
            ],
            use_container_width=True, hide_index=True,
        )
    else:
        st.success("No open Knowledge Gaps.")

    pre = snapshot.get("pre_enrichment")
    if pre is not None:
        st.write("")
        st.caption(
            f"Initial position at intake: KCS {pre['kcs'] * 100:.0f}% · KQS {pre['kqs'] * 100:.0f}% "
            "(preserved for before/current comparison in Gap Closure and Assurance Result)."
        )


# ---------------------------------------------------------------------------
# 4. Gap Closure
# ---------------------------------------------------------------------------

def render_gap_closure(client: ApiClient, summary: dict) -> None:
    st.subheader("Guided Gap Closure")
    st.caption("Which gaps matter most, what the system asks the SME, and how revalidation moves the assurance position.")

    stage = summary.get("stage")
    if stage in (None, "START", "INGESTED"):
        st.info("Complete Knowledge Assurance validation first.")
        return

    snapshot = client.get_demo_assurance_snapshot()
    pre = snapshot.get("pre_enrichment")
    current = snapshot.get("current")

    if pre is not None and current is not None:
        st.markdown("**Before → Current**")
        cols = st.columns(4)
        with cols[0]:
            st.metric("Knowledge Gaps (open)", current["critical_unresolved_gaps"],
                       delta=current["critical_unresolved_gaps"] - pre["critical_unresolved_gaps"], delta_color="inverse")
        with cols[1]:
            st.metric("KCS", f"{current['kcs'] * 100:.0f}%", delta=f"{(current['kcs'] - pre['kcs']) * 100:+.0f}pp")
        with cols[2]:
            st.metric("KQS", f"{current['kqs'] * 100:.0f}%", delta=f"{(current['kqs'] - pre['kqs']) * 100:+.0f}pp")
        with cols[3]:
            st.metric("Closure Rounds Completed", summary.get("closure_rounds_completed", 0))
        st.markdown(
            _gate_badge(current["sufficiency_gate_passed"], "Sufficiency Gate") + "&nbsp;&nbsp;" +
            (_gate_badge(current["quality_gate_passed"], "Quality Gate") if current["quality_gate_applicable"] else ""),
            unsafe_allow_html=True,
        )

    st.write("")
    if stage not in ("ASSURANCE_COMPLETE", "ASSESSMENT_COMPLETE"):
        action_cols = st.columns(2)
        with action_cols[0]:
            if st.button("Apply SME Response & Revalidate", type="primary", key="gap_closure_advance_one"):
                try:
                    client.advance_demo_enrichment(max_rounds=1)
                except ApiError as exc:
                    st.error(f"Could not advance gap closure: {exc.message}")
                    return
                st.rerun()
        with action_cols[1]:
            if st.button("Run Remaining Closure", key="gap_closure_advance_all"):
                try:
                    client.advance_demo_enrichment(max_rounds=50)
                    client.complete_demo_assurance()
                except ApiError as exc:
                    st.error(f"Could not complete gap closure: {exc.message}")
                    return
                st.rerun()
    else:
        st.success("Gap closure complete — the Sufficiency and Quality Gates have been evaluated.")

    history = client.get_demo_closure_history().get("history", [])
    st.write("")
    st.markdown("**Representative Remediation Interactions**")
    if not history:
        st.caption("No closure interactions have been applied yet.")
        return

    # Select up to 6 representative interactions across distinct themes,
    # newest-first within each theme, rather than showing the entire
    # real history (which may contain more rounds than are useful to
    # present individually) -- aggregate progress above already reflects
    # every real round, highlighted or not.
    seen_themes: set[str] = set()
    representative = []
    for entry in reversed(history):
        if entry["rule_family"] not in seen_themes:
            representative.append(entry)
            seen_themes.add(entry["rule_family"])
        if len(representative) >= 6:
            break
    representative.reverse()

    st.caption(
        f"Showing {len(representative)} representative interaction(s) across distinct remediation themes, "
        f"out of {len(history)} real closure round(s) applied."
    )

    for entry in representative:
        with st.container():
            st.markdown(
                f"""
                <div style="background-color:{CARD_BG};border:1px solid {BORDER};
                border-radius:8px;padding:14px 18px;margin-bottom:10px;">
                    <div style="font-weight:700;font-size:1.05em;">{entry['object_name']}
                        &nbsp;{badge_html(entry['object_type'] or '', MUTED)}
                        &nbsp;{badge_html(rule_family_label(entry['rule_family']), "#6D706B")}</div>
                    <div style="margin-top:4px;">Criticality: {entry['criticality'] or '—'} &nbsp;|&nbsp;
                        Risk: {entry['risk_level'] or '—'}</div>
                    <div style="margin-top:8px;"><b>Question:</b> {entry['question']}</div>
                    <div style="margin-top:4px;"><b>Deterministic SME Response:</b> {entry['sme_response'] or '—'}</div>
                    <div style="margin-top:8px;color:{MUTED};">
                        KCS {entry['kcs_before'] * 100:.0f}% → {entry['kcs_after'] * 100:.0f}%
                        &nbsp;|&nbsp; KQS {entry['kqs_before'] * 100:.0f}% → {entry['kqs_after'] * 100:.0f}%
                        &nbsp;|&nbsp; {entry['resolved_finding_count']} finding(s) resolved
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )


# ---------------------------------------------------------------------------
# 5. Assurance Result
# ---------------------------------------------------------------------------

def render_assurance_result(client: ApiClient, summary: dict) -> None:
    st.subheader("Assurance Result")
    st.caption("The package has passed from extracted knowledge to assured transition knowledge.")

    stage = summary.get("stage")
    if stage in (None, "START", "INGESTED", "VALIDATED"):
        st.info("Complete Gap Closure to reach the final assurance result.")
        return

    snapshot = client.get_demo_assurance_snapshot()
    current = snapshot.get("current")
    if current is None:
        st.info("No assurance result available yet.")
        return

    cols = st.columns(2)
    with cols[0]:
        st.metric("Final KCS", f"{current['kcs'] * 100:.0f}%")
    with cols[1]:
        st.metric("Final KQS", f"{current['kqs'] * 100:.0f}%")

    st.markdown("**Final Dimension Breakdown**")
    _dimension_row(current)

    st.write("")
    st.markdown(
        _gate_badge(current["sufficiency_gate_passed"], "Sufficiency Gate") + "&nbsp;&nbsp;" +
        (_gate_badge(current["quality_gate_passed"], "Quality Gate") if current["quality_gate_applicable"] else ""),
        unsafe_allow_html=True,
    )

    gap_cols = st.columns(2)
    with gap_cols[0]:
        st.metric("Open Knowledge Gaps", current["critical_unresolved_gaps"])
    with gap_cols[1]:
        st.metric("Transition Risks", current["transition_risks"])

    st.write("")
    st.markdown("**Transition Risks**")
    risks = current.get("transition_risk_detail", [])
    if not risks:
        st.success("No open material transition risks derived from unresolved knowledge gaps.")
    else:
        for risk in risks:
            st.markdown(
                f"""
                <div style="background-color:{CARD_BG};border:1px solid {BORDER};
                border-radius:8px;padding:12px 16px;margin-bottom:8px;">
                    <div style="font-weight:700;">{risk['operational_scenario'].replace('_', ' ').title()}
                        &nbsp;{badge_html(risk['severity'], "#FFAD28" if risk['severity'] != "Low" else "#3D6B4F")}</div>
                    <div style="margin-top:4px;">{risk['description']}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.write("")
    st.markdown("**Traceability**")
    trace = client.get_demo_traceability_example().get("example")
    if trace is None:
        st.caption("No remediation interaction has occurred yet, so no traceability chain is available.")
    else:
        st.markdown(
            f"Profile `{trace['profile_id']}` → rule **{rule_family_label(trace['rule_family'])}** → "
            f"object **{trace['object_name']}** ({trace['object_type']}) → Finding resolved → "
            f"Knowledge Gap *\u201c{trace['question']}\u201d* → SME response *\u201c{trace['sme_response']}\u201d* → "
            f"{trace['resolved_finding_count']} finding(s) resolved."
        )

    if stage == "ENRICHING":
        st.write("")
        if st.button("Complete Assurance", type="primary", key="assurance_result_complete"):
            try:
                client.complete_demo_assurance()
            except ApiError as exc:
                st.error(f"Could not complete assurance: {exc.message}")
                return
            st.rerun()
    elif stage in ("ASSURANCE_COMPLETE", "ASSESSMENT_COMPLETE"):
        st.success("The package is assured and ready to continue into Receiver Assessment (UI Phase 3).")
