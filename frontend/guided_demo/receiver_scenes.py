"""
frontend/guided_demo/receiver_scenes.py — Receiver Assessment,
Competency Evidence, Readiness Decision, and Executive Recommendation
scenes (UI Phase 3, issue_log #20).

Read-mostly over frontend.api_client.ApiClient.get_demo_receiver_assessment_detail()
(which itself only reads/recomputes real persisted KASE/KRA outputs --
see services/demo/hierarchical_demo_orchestrator.py). The only new
computation on this side is simple, deterministic presentation
grouping (evidence-quality labels, strengths/development areas,
recommendation copy) -- never a second scoring/threshold/certification
engine. config is imported directly for config.COMPETENCY_CATALOG/
config.OIS_WEIGHTS (the full 12-competency catalog + criticality/
pillar/weight metadata) -- the same precedent frontend/theme.py already
established for config.COLORS; config is not a services/models/database
module, so this does not violate the mechanically-enforced frontend
boundary (tests/test_frontend_boundary.py).
"""

import config
import streamlit as st

from frontend.api_client import ApiClient, ApiError
from frontend.guided_demo.presentation_labels import (
    EVIDENCE_QUALITY_COLORS,
    competency_label,
    evidence_quality_label,
    pillar_label,
)
from frontend.theme import BORDER, CARD_BG, MUTED, badge_html, decision_color


def _status_badge(overall_status: str) -> str:
    colors = {"Demonstrated": "#3D6B4F", "Partial": "#FFAD28", "Weak": "#FF4F59"}
    return badge_html(overall_status, colors.get(overall_status, MUTED))


# ---------------------------------------------------------------------------
# Scene 1 — Receiver Assessment Setup
# ---------------------------------------------------------------------------

def render_receiver_assessment_setup(client: ApiClient, summary: dict) -> str:
    """Returns the currently-selected participant_id."""
    st.subheader("Receiver Assessment Setup")
    st.caption("One assured knowledge package. Three receivers. Three different readiness outcomes.")

    assurance = summary.get("assurance")
    if assurance is None:
        st.info("Complete Knowledge Assurance and Gap Closure first.")
        return ""

    cols = st.columns(4)
    with cols[0]:
        st.metric("Knowledge Assurance", "Assured" if assurance["sufficiency_gate_passed"] else "In Progress")
    with cols[1]:
        st.metric("KCS", f"{assurance['kcs'] * 100:.0f}%")
    with cols[2]:
        st.metric("KQS", f"{assurance['kqs'] * 100:.0f}%")
    with cols[3]:
        st.metric("Open Knowledge Gaps", assurance["critical_unresolved_gaps"])

    st.write("")
    receivers = summary.get("receivers", {})
    receiver_ids = list(receivers.keys())
    if not receiver_ids:
        st.info("No pinned receivers found.")
        return ""

    selected_id = st.session_state.get("guided_demo_selected_participant_id", receiver_ids[0])
    if selected_id not in receiver_ids:
        selected_id = receiver_ids[0]

    cols = st.columns(len(receiver_ids))
    for col, pid in zip(cols, receiver_ids):
        r = receivers[pid]
        with col:
            is_assessed = r.get("status") == "assessed"
            status_text = (
                badge_html(f"{r['final_decision']} · OIS {r['ois_score']:.1f}", decision_color(r["final_decision"]))
                if is_assessed else badge_html("Not Assessed", MUTED)
            )
            st.markdown(
                f"""
                <div style="background-color:{CARD_BG};border:1px solid {BORDER};
                border-radius:8px;padding:14px;text-align:center;">
                    <div style="font-weight:700;">{r['name']}</div>
                    <div style="margin-top:8px;">{status_text}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button("Select", key=f"select_{pid}", use_container_width=True):
                st.session_state["guided_demo_selected_participant_id"] = pid
                st.rerun()

    st.write("")
    receiver_name = receivers[selected_id]["name"]
    st.markdown(f"**Selected receiver:** {receiver_name}")

    if receivers[selected_id].get("status") != "assessed":
        if st.button(f"Run Real Assessment for {receiver_name}", type="primary", key="run_assessment"):
            try:
                client.assess_demo_receiver(selected_id)
            except ApiError as exc:
                st.error(f"Could not run the assessment: {exc.message}")
                return selected_id
            st.rerun()
    else:
        st.success(f"{receiver_name} has already been assessed against the real KASE/KRA pipeline.")

    return selected_id


# ---------------------------------------------------------------------------
# Scene 2 — Assessment Experience
# ---------------------------------------------------------------------------

def render_assessment_experience(client: ApiClient, participant_id: str) -> None:
    st.subheader("Assessment Experience")
    st.caption("How KASE evaluates the selected receiver against the real generated scenario set.")

    if not participant_id:
        st.info("Select a receiver in Receiver Assessment Setup first.")
        return

    detail = client.get_demo_receiver_assessment_detail(participant_id)
    if detail["status"] != "assessed":
        if detail["scenario_count"]:
            st.caption(f"{detail['scenario_count']} real scenario(s) already generated for this package.")
        else:
            st.info("Run the real assessment in Receiver Assessment Setup to generate scenarios.")
        return

    cols = st.columns(4)
    with cols[0]:
        st.metric("Scenarios Generated", detail["scenario_count"])
    with cols[1]:
        st.metric("Categories", len(detail["categories"]))
    with cols[2]:
        st.metric("Competencies Exercised", len(detail["competencies_exercised"]))
    with cols[3]:
        critical = [c for c in detail["competencies_exercised"] if config.COMPETENCY_CATALOG.get(c, {}).get("is_critical")]
        st.metric("Critical Competencies Assessed", len(critical))

    st.write("")
    st.markdown("**Representative Assessment Interactions**")
    interactions = detail["representative_interactions"]
    if not interactions:
        st.caption("No representative interactions available.")
        return

    varies = len({i["overall_status"] for i in interactions}) > 1
    if varies:
        st.caption(
            "This receiver performs strongly in some situations and only partially in others — "
            "the representative interactions below are selected to show that real variation."
        )

    for interaction in interactions:
        competencies = ", ".join(competency_label(c) for c in interaction["competency_mapping"])
        st.markdown(
            f"""
            <div style="background-color:{CARD_BG};border:1px solid {BORDER};
            border-radius:8px;padding:14px 18px;margin-bottom:10px;">
                <div style="font-weight:700;">{interaction['category']} Scenario
                    &nbsp;{_status_badge(interaction['overall_status'])}</div>
                <div style="margin-top:6px;"><b>Situation:</b> {interaction['trigger']}</div>
                <div style="margin-top:4px;"><b>Decision point:</b> {interaction['decision_point']}</div>
                <div style="margin-top:6px;"><b>Receiver response:</b> {interaction['response_text']}</div>
                <div style="margin-top:6px;color:{MUTED};">Competencies: {competencies}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# Scene 3 — Competency Evidence Profile
# ---------------------------------------------------------------------------

def render_competency_profile(client: ApiClient, participant_id: str) -> None:
    st.subheader("Competency Evidence Profile")
    st.caption("How scenario evidence becomes a receiver capability profile.")

    if not participant_id:
        st.info("Select a receiver in Receiver Assessment Setup first.")
        return

    detail = client.get_demo_receiver_assessment_detail(participant_id)
    if detail["status"] != "assessed":
        st.info("Run the real assessment in Receiver Assessment Setup first.")
        return

    # A. OIS hero metric
    st.metric("Operational Independence Score (OIS)", f"{detail['ois_score']:.1f}")

    # B. Critical Competency Gate status
    gate_passed = detail["critical_competency_gate_passed"]
    st.markdown(
        badge_html(
            f"Critical Competency Gate: {'Pass' if gate_passed else 'Fail'}",
            "#3D6B4F" if gate_passed else "#FF4F59",
        ),
        unsafe_allow_html=True,
    )

    # C. Pillar scores
    st.write("")
    st.markdown("**Pillar Scores**")
    pillar_scores = {pillar_label(k): v for k, v in detail["pillar_scores"].items()}
    if pillar_scores:
        st.bar_chart(pillar_scores)

    # D. Competency evidence matrix
    st.markdown("**Competency Evidence Matrix**")
    rows = []
    for name, info in config.COMPETENCY_CATALOG.items():
        if name not in detail["competencies_exercised"]:
            continue
        score = detail["competency_scores"].get(name)
        rows.append({
            "Competency": competency_label(name),
            "Pillar": pillar_label(info["pillar"]),
            "Critical": "Yes" if info["is_critical"] else "No",
            "Score": f"{score:.0f}" if score is not None else "—",
            "Evidence Quality": evidence_quality_label(score),
        })
    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)

    not_exercised = [
        competency_label(name) for name in config.COMPETENCY_CATALOG
        if name not in detail["competencies_exercised"]
    ]
    if not_exercised:
        st.caption(
            f"Not exercised by this package's real generated scenarios (not assessed, not failed): "
            f"{', '.join(not_exercised)}."
        )

    # E. Strengths and Development Areas -- simple deterministic rules over
    # the real scores, no new scoring engine.
    st.write("")
    strengths_col, development_col = st.columns(2)
    scored = [
        (name, score) for name, score in detail["competency_scores"].items() if score is not None
    ]
    strengths = sorted(scored, key=lambda x: -x[1])[:3]
    development = sorted(
        [(n, s) for n, s in scored if s < 85],
        key=lambda x: x[1],
    )[:3]
    with strengths_col:
        st.markdown("**Strengths**")
        if strengths:
            for name, score in strengths:
                st.markdown(f"- {competency_label(name)} ({score:.0f})")
        else:
            st.caption("No scored competencies yet.")
    with development_col:
        st.markdown("**Development Areas**")
        if development:
            for name, score in development:
                critical_tag = " (Critical)" if config.COMPETENCY_CATALOG.get(name, {}).get("is_critical") else ""
                st.markdown(f"- {competency_label(name)}{critical_tag} ({score:.0f})")
        else:
            st.caption("No development areas identified — all scored competencies at or above 85.")


# ---------------------------------------------------------------------------
# Scene 4 — Readiness Decision
# ---------------------------------------------------------------------------

def render_readiness_decision(client: ApiClient, participant_id: str) -> None:
    st.subheader("Readiness Decision")
    st.caption("Knowledge Assurance + Receiver Competency Assessment + OIS Threshold Evaluation = Readiness Decision")

    if not participant_id:
        st.info("Select a receiver in Receiver Assessment Setup first.")
        return

    detail = client.get_demo_receiver_assessment_detail(participant_id)
    if detail["status"] != "assessed":
        st.info("Run the real assessment in Receiver Assessment Setup first.")
        return

    summary = client.get_demo_summary()
    assurance = summary.get("assurance") or {}

    st.markdown("**Decision Inputs (all real, from the backend)**")
    cols = st.columns(3)
    with cols[0]:
        st.markdown("*Knowledge Assurance*")
        st.markdown(badge_html("Sufficiency Gate: " + ("Pass" if assurance.get("sufficiency_gate_passed") else "Fail"),
                                "#3D6B4F" if assurance.get("sufficiency_gate_passed") else "#FF4F59"), unsafe_allow_html=True)
        st.markdown(badge_html("Quality Gate: " + ("Pass" if assurance.get("quality_gate_passed") else "Fail"),
                                "#3D6B4F" if assurance.get("quality_gate_passed") else "#FF4F59"), unsafe_allow_html=True)
    with cols[1]:
        st.markdown("*Receiver Competency*")
        gate = detail["critical_competency_gate_passed"]
        st.markdown(badge_html("Critical Competency Gate: " + ("Pass" if gate else "Fail"),
                                "#3D6B4F" if gate else "#FF4F59"), unsafe_allow_html=True)
        st.markdown(badge_html("Open Gap Gate: " + ("Pass" if detail["open_gap_gate_passed"] else "Fail"),
                                "#3D6B4F" if detail["open_gap_gate_passed"] else "#FF4F59"), unsafe_allow_html=True)
    with cols[2]:
        st.markdown("*OIS Threshold*")
        st.metric("OIS", f"{detail['ois_score']:.1f}", delta=f"vs. threshold {detail['effective_threshold']}")
        if detail["boundary_zone_applied"]:
            st.caption("Within the boundary zone below the readiness threshold.")

    st.write("")
    st.markdown("**Decision**")
    decision = detail["final_decision"]
    st.markdown(
        f'<div style="background-color:{decision_color(decision)};color:#FFFFFF;'
        f'padding:16px 20px;border-radius:8px;font-size:1.2em;font-weight:700;text-align:center;">'
        f'{decision}{" · " + detail["certification_level"] if detail["certification_level"] else ""}</div>',
        unsafe_allow_html=True,
    )

    st.write("")
    if decision == "Ready":
        st.markdown(
            f"**Why Ready:** OIS {detail['ois_score']:.1f} meets or exceeds the {detail['effective_threshold']} "
            "threshold, the Critical Competency Gate passes, and all Knowledge Assurance gates pass."
        )
    elif decision == "Conditionally Ready":
        st.markdown(
            f"**Why Conditionally Ready:** OIS {detail['ois_score']:.1f} is below the {detail['effective_threshold']} "
            "threshold but within the configured boundary zone, and all required gates (Critical Competency, "
            "Sufficiency, Quality, Open Gap) pass."
        )
    elif decision == "Not Ready":
        if not detail["critical_competency_gate_passed"]:
            st.markdown(
                "**Why Not Ready:** the Critical Competency Gate fails — one or more critical competencies "
                "scored below the required floor. This controls the decision regardless of OIS."
            )
        else:
            st.markdown(
                f"**Why Not Ready:** OIS {detail['ois_score']:.1f} falls below the {detail['effective_threshold']} "
                "threshold and outside the boundary zone."
            )


# ---------------------------------------------------------------------------
# Scene 5 — Executive Recommendation
# ---------------------------------------------------------------------------

def render_executive_recommendation(client: ApiClient, participant_id: str) -> None:
    st.subheader("Executive Recommendation")

    if not participant_id:
        st.info("Select a receiver in Receiver Assessment Setup first.")
        return

    detail = client.get_demo_receiver_assessment_detail(participant_id)
    if detail["status"] != "assessed":
        st.info("Run the real assessment in Receiver Assessment Setup first.")
        return

    decision = detail["final_decision"]
    development = sorted(
        [(n, s) for n, s in detail["competency_scores"].items() if s is not None and s < 85],
        key=lambda x: x[1],
    )

    if decision == "Ready":
        recommendation = (
            "Proceed with transition according to the planned transition schedule, "
            "with normal post-transition monitoring."
        )
    elif decision == "Conditionally Ready":
        areas = ", ".join(competency_label(n) for n, _ in development[:3]) or "the identified capability areas"
        recommendation = (
            f"Proceed only with controlled transition conditions and targeted remediation of {areas}, "
            "followed by reassessment."
        )
    else:
        failing_critical = [
            competency_label(n) for n, s in detail["competency_scores"].items()
            if s is not None and s < 70 and config.COMPETENCY_CATALOG.get(n, {}).get("is_critical")
        ]
        areas = ", ".join(failing_critical) or "the failing critical competency areas"
        recommendation = (
            f"Hold transition ownership transfer, address {areas}, collect new evidence, "
            "and reassess before transition approval."
        )

    st.markdown(
        f"""
        <div style="background-color:{CARD_BG};border:1px solid {BORDER};border-radius:8px;
        padding:16px 20px;">
            <div style="font-weight:700;margin-bottom:8px;">Recommendation</div>
            <div>{recommendation}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.write("")
    st.markdown("**Decision Summary**")
    st.markdown(f"1. **Can transition proceed?** {'Yes' if decision != 'Not Ready' else 'Not at this time'}")
    st.markdown(f"2. **Under what conditions?** {'Standard' if decision == 'Ready' else 'Controlled/remediated' if decision == 'Conditionally Ready' else 'Hold until reassessed'}")
    st.markdown("3. **What should happen next?** " + recommendation.split(",")[0] + ".")
    if development:
        areas = ", ".join(competency_label(n) for n, _ in development[:5])
        st.markdown(f"4. **Capability areas requiring attention:** {areas}")
    else:
        st.markdown("4. **Capability areas requiring attention:** none identified.")
    st.markdown(
        "5. **Evidence that would justify reassessment:** demonstrated evidence (score ≥ 85) on the "
        "development areas above, collected through real scenario responses and revalidated by KASE."
    )


# ---------------------------------------------------------------------------
# Cross-Receiver Comparison
# ---------------------------------------------------------------------------

def render_cross_receiver_comparison(client: ApiClient, summary: dict) -> None:
    st.subheader("Cross-Receiver Comparison")
    st.caption("Knowledge assurance is package-level. Readiness is receiver-specific.")

    receivers = summary.get("receivers", {})
    rows = []
    for pid, r in receivers.items():
        if r.get("status") != "assessed":
            rows.append({"Receiver": r["name"], "OIS": "—", "Critical Gate": "—", "Decision": "Not Assessed",
                         "Certification": "—", "Boundary Zone": "—", "Strengths": "—", "Development Areas": "—"})
            continue
        detail = client.get_demo_receiver_assessment_detail(pid)
        scored = [(n, s) for n, s in detail["competency_scores"].items() if s is not None]
        strengths = ", ".join(competency_label(n) for n, _ in sorted(scored, key=lambda x: -x[1])[:2])
        development = ", ".join(
            competency_label(n) for n, s in sorted([(n, s) for n, s in scored if s < 85], key=lambda x: x[1])[:2]
        )
        rows.append({
            "Receiver": r["name"],
            "OIS": f"{detail['ois_score']:.1f}",
            "Critical Gate": "Pass" if detail["critical_competency_gate_passed"] else "Fail",
            "Decision": detail["final_decision"],
            "Certification": detail["certification_level"] or "—",
            "Boundary Zone": "Yes" if detail["boundary_zone_applied"] else "No",
            "Strengths": strengths or "—",
            "Development Areas": development or "None",
        })

    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)

    assessed_count = sum(1 for r in receivers.values() if r.get("status") == "assessed")
    if assessed_count == len(receivers) and receivers:
        decisions = {r["final_decision"] for r in receivers.values()}
        if len(decisions) > 1:
            st.info(
                "The same assured knowledge package produced 3 different readiness outcomes — "
                "assurance is package-level, readiness is receiver-specific."
            )
