"""
tests/test_session29_explanation_engine.py — Phase 9 / Session 29 success
criteria: the Explanation Engine's three layers plus traceability tree,
built end-to-end off real score_and_persist_readiness (Session 28)
output, the same integration pattern test_session28_kase_integration.py
uses.

Covers:
  1. A grep-based test that services/explanation_data_layer.py never
     applies +, *, /, or sum() to a score field (the [FROZEN] hard rule).
  2. ExplanationTemplateLayer.render() determinism across repeated calls.
  3. A Chunk-6-style fixture (one failing critical competency, missing
     markers) reproducing the frozen sentence and "Not Ready".
  4. The narrative number-guard rejecting a planted bad number and
     falling back to the deterministic template text.
  5. TraceabilityService.build_tree() resolving all seven levels,
     including the relationship-sourced knowledge-object path.
  6. ExplanationEngine.explain() end-to-end off a real KASE rollup.
"""

import json
import re

import pytest

import config
from models import (
    AssessmentPackage,
    GapRecord,
    OISResult,
    Participant,
    ReceiverReadiness,
    Scenario as ScenarioRow,
    ScenarioResponse,
)
from models.coverage import CoverageResult
from schemas.explanation import CompetencyFact, EvidenceFact, ExplanationData, GateFact, PillarFact
from services.claude_client import ClaudeClient
from services.explanation_data_layer import ExplanationDataLayer
from services.explanation_engine import ExplanationEngine, ExplanationResult
from services.explanation_narrative_layer import ContextualNarrative, ExplanationNarrativeLayer
from services.explanation_template_layer import ExplanationTemplateLayer, TemplateNarrative
from services.graph_storage import save_graph_version
from services.kase import score_and_persist_readiness
from services.knowledge_model import validate_object, validate_relationship
from services.traceability_service import TraceabilityService, TraceNode
from utils.errors import NarrativeNumberViolation

_MARKER_TEXT = "alpha bravo charlie delta echo"
_DEMONSTRATED_RESPONSE = "alpha bravo charlie report filed"  # 3/5 -> ratio 0.6
_MISSING_RESPONSE = "report filed today nothing"  # 0/5 -> ratio 0.0

_RESPONSE_FOR = {
    "Demonstrated": _DEMONSTRATED_RESPONSE,
    "Missing": _MISSING_RESPONSE,
}

# Exactly one failing critical competency (System Operation, critical,
# OE pillar) -> mirrors the Chunk 6 worked-example shape (one critical
# competency below threshold drives the whole "Not Ready" sentence).
# Every other competency Demonstrated so only one reason token fires.
_SET_NOT_READY = {name: "Demonstrated" for name in config.COMPETENCY_CATALOG}
_SET_NOT_READY["System Operation"] = "Missing"


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def sample_participant(db_session, sample_program):
    participant = Participant(
        program_id=sample_program.id, name="Test Receiver", participant_type="Receiver"
    )
    db_session.add(participant)
    db_session.flush()
    return participant


@pytest.fixture()
def graph_version_id(db_session, sample_package):
    version_row, _ = save_graph_version(
        db_session,
        sample_package.id,
        [
            validate_object({"id": "p1", "object_type": "Process", "name": "Proc One", "criticality": "Important"}),
            validate_object({"id": "t1", "object_type": "Task", "name": "Task One", "criticality": "Important"}),
        ],
        [validate_relationship({"id": "r1", "relationship_type": "HAS_TASK", "source_id": "p1", "target_id": "t1"})],
    )
    return version_row.id


@pytest.fixture()
def assessment_package_id(db_session, sample_package, graph_version_id):
    package = AssessmentPackage(
        package_id=sample_package.id, graph_version_id=graph_version_id, status="Validated"
    )
    db_session.add(package)
    db_session.flush()
    return package.id


def _build_scenario_responses(
    db_session, assessment_package_id, participant_id, competency_status_map, source_for=None
):
    """One Scenario (+ one matching ScenarioResponse) per competency,
    engineered onto the intended detection_status. `source_for` optionally
    maps competency_name -> (source_kind, source_id) so specific scenarios
    carry traceability back to a real graph element; everything else is
    left untracked (source_kind=None), matching legacy rows."""
    source_for = source_for or {}
    pairs = []
    for competency_name, status in competency_status_map.items():
        source_kind, source_id = source_for.get(competency_name, (None, None))
        scenario = ScenarioRow(
            assessment_package_id=assessment_package_id,
            source_kind=source_kind,
            source_id=source_id,
            category="Operational",
            difficulty="L2",
            situation=f"Situation for {competency_name}",
            expected_evidence_json=json.dumps([_MARKER_TEXT]),
            competency_mapping_json=json.dumps([competency_name]),
            validation_status="Passed",
        )
        db_session.add(scenario)
        db_session.flush()

        response = ScenarioResponse(
            scenario_id=scenario.id,
            participant_id=participant_id,
            response_text=_RESPONSE_FOR[status],
        )
        db_session.add(response)
        db_session.flush()

        pairs.append((scenario, response))
    return pairs


def _coverage_result(db_session, sample_package, graph_version_id, sufficiency_gate_passed=True):
    cr = CoverageResult(
        package_id=sample_package.id,
        graph_version_id=graph_version_id,
        coverage_score=0.9 if sufficiency_gate_passed else 0.4,
        sufficiency_gate_passed=sufficiency_gate_passed,
    )
    db_session.add(cr)
    db_session.flush()
    return cr


@pytest.fixture()
def not_ready_readiness_id(db_session, sample_package, sample_participant, assessment_package_id, graph_version_id):
    """A full KASE rollup with exactly one failing critical competency
    (System Operation) and two scenarios traced back to real graph
    elements: one object-sourced (Process Execution -> p1) and one
    relationship-sourced (Task Sequencing -> r1, which resolves to
    p1/t1)."""
    pairs = _build_scenario_responses(
        db_session,
        assessment_package_id,
        sample_participant.id,
        _SET_NOT_READY,
        source_for={
            "Process Execution": ("object", "p1"),
            "Task Sequencing": ("relationship", "r1"),
        },
    )
    coverage_result = _coverage_result(db_session, sample_package, graph_version_id)

    rollup = score_and_persist_readiness(
        db_session,
        package_id=sample_package.id,
        participant_id=sample_participant.id,
        role_tier="Primary",
        scenario_responses=pairs,
        gaps=[],
        coverage_result=coverage_result,
    )
    assert rollup.threshold_resolution.decision == "Not Ready"
    return rollup.receiver_readiness_id


# ---------------------------------------------------------------------------
# 1. [FROZEN] hard rule: no score-field arithmetic in the data layer
# ---------------------------------------------------------------------------

def test_data_layer_never_applies_arithmetic_to_score_fields():
    with open("services/explanation_data_layer.py", encoding="utf-8") as f:
        lines = f.readlines()

    in_docstring = False
    violations = []
    for lineno, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith('"""') or stripped.startswith("'''"):
            # toggle (handles single-line docstrings as a no-op toggle pair)
            in_docstring = not in_docstring if stripped.count('"""') % 2 == 1 or stripped.count("'''") % 2 == 1 else in_docstring
            continue
        if in_docstring or stripped.startswith("#"):
            continue
        if "sum(" in line:
            violations.append((lineno, line))
            continue
        if "score" in line.lower() and re.search(r"[+*/]", line):
            violations.append((lineno, line))

    assert violations == [], f"Score-field arithmetic found: {violations}"


# ---------------------------------------------------------------------------
# 2. ExplanationTemplateLayer determinism
# ---------------------------------------------------------------------------

def _sample_explanation_data() -> ExplanationData:
    competency = CompetencyFact(
        competency_id="System Operation",
        name="System Operation",
        score=62.0,
        weight=0.5,
        is_critical=True,
        critical_threshold=70.0,
        passed_gate=False,
        evidence=[
            EvidenceFact(marker_id="EH-03", state="Missing", score=0.0, scenario_id="s1", knowledge_object_ids=[]),
            EvidenceFact(marker_id="EH-04", state="Missing", score=0.0, scenario_id="s1", knowledge_object_ids=[]),
            EvidenceFact(marker_id="EH-06", state="Missing", score=0.0, scenario_id="s1", knowledge_object_ids=[]),
        ],
    )
    pillar = PillarFact(
        pillar_id="OE", name="Operational Execution", score=62.0, weight=0.4, competencies=[competency]
    )
    return ExplanationData(
        receiver_readiness_id="r1",
        package_id="p1",
        receiver_id="part1",
        receiver_role="Primary",
        coverage=0.9,
        ois=62.0,
        ois_recomputed=62.0,
        readiness_decision="Not Ready",
        certification=None,
        pillars=[pillar],
        gates=[
            GateFact(gate_id="critical_competency", passed=False, observed=62.0, threshold=70.0, failing_items=["System Operation"]),
        ],
        primary_failure_reasons=["critical_competency:System Operation"],
    )


def test_template_layer_is_deterministic():
    data = _sample_explanation_data()
    layer = ExplanationTemplateLayer()
    first = layer.render(data)
    second = layer.render(data)
    assert first == second
    assert isinstance(first, TemplateNarrative)


def test_template_layer_reproduces_frozen_chunk6_sentence():
    data = _sample_explanation_data()
    template = ExplanationTemplateLayer().render(data)

    assert template.decision_sentence == (
        "Receiver is NOT READY because System Operation scored 62, "
        "below the critical threshold of 70."
    )
    assert template.missing_evidence_sentences == ["Missing evidence: EH-03, EH-04, EH-06."]


# ---------------------------------------------------------------------------
# 3. Real end-to-end data layer build against a KASE rollup
# ---------------------------------------------------------------------------

def test_data_layer_build_yields_not_ready_with_one_failing_competency(db_session, not_ready_readiness_id):
    data = ExplanationDataLayer(db_session).build(not_ready_readiness_id)

    assert isinstance(data, ExplanationData)
    assert data.readiness_decision == "Not Ready"
    assert data.primary_failure_reasons == ["critical_competency:System Operation"]

    system_op = next(
        c for pillar in data.pillars for c in pillar.competencies if c.competency_id == "System Operation"
    )
    assert system_op.score == 0.0
    assert system_op.passed_gate is False
    assert system_op.critical_threshold == config.CRITICAL_COMPETENCY_GATE_THRESHOLD


def test_data_layer_resolves_object_and_relationship_sourced_scenarios(db_session, not_ready_readiness_id):
    data = ExplanationDataLayer(db_session).build(not_ready_readiness_id)

    process_execution = next(
        c for pillar in data.pillars for c in pillar.competencies if c.competency_id == "Process Execution"
    )
    assert process_execution.evidence[0].knowledge_object_ids == ["p1"]

    task_sequencing = next(
        c for pillar in data.pillars for c in pillar.competencies if c.competency_id == "Task Sequencing"
    )
    assert sorted(task_sequencing.evidence[0].knowledge_object_ids) == ["p1", "t1"]


def test_data_layer_raises_explanation_data_error_when_unscored(db_session):
    from utils.errors import ExplanationDataError

    with pytest.raises(ExplanationDataError):
        ExplanationDataLayer(db_session).build("does-not-exist")


# ---------------------------------------------------------------------------
# 4. Narrative layer number-guard
# ---------------------------------------------------------------------------

class _StubClaudeClient:
    """Duck-typed stand-in for ClaudeClient.complete -- returns whatever
    narrative the test wants, independent of mock_response/cache, to
    deterministically exercise the number-guard's accept/reject paths."""

    def __init__(self, narrative_text):
        self.narrative_text = narrative_text

    def complete(self, **kwargs):
        return {"narrative": self.narrative_text}


def test_guard_rejects_planted_bad_number_and_falls_back():
    data = _sample_explanation_data()
    template = ExplanationTemplateLayer().render(data)

    bad_client = _StubClaudeClient("This receiver scored an impressive 999 overall.")
    layer = ExplanationNarrativeLayer(bad_client)
    result = layer.generate(data, template)

    assert isinstance(result, ContextualNarrative)
    assert result.fell_back is True
    assert result.used_claude is False
    assert result.text == layer._fallback_text(template)


def test_guard_accepts_narrative_using_only_traceable_numbers():
    data = _sample_explanation_data()
    template = ExplanationTemplateLayer().render(data)

    good_client = _StubClaudeClient(
        "System Operation scored 62, short of the 70 threshold required for this critical competency."
    )
    layer = ExplanationNarrativeLayer(good_client)
    result = layer.generate(data, template)

    assert result.used_claude is True
    assert result.fell_back is False


# ---------------------------------------------------------------------------
# 5. Traceability tree -- all seven levels, both resolution paths
# ---------------------------------------------------------------------------

def test_traceability_tree_resolves_all_seven_levels(db_session, not_ready_readiness_id):
    data = ExplanationDataLayer(db_session).build(not_ready_readiness_id)
    tree = TraceabilityService(db_session).build_tree(data)

    assert isinstance(tree, TraceNode)
    assert tree.level == "readiness"
    ois_node = tree.children[0]
    assert ois_node.level == "ois"

    pillar_node = next(p for p in ois_node.children if p.id == "OE")
    competency_node = next(c for c in pillar_node.children if c.id == "Process Execution")
    evidence_node = competency_node.children[0]
    assert evidence_node.level == "evidence"
    scenario_node = evidence_node.children[0]
    assert scenario_node.level == "scenario"
    ko_ids = {child.id for child in scenario_node.children}
    assert ko_ids == {"p1"}

    # Relationship-sourced path: Task Sequencing's scenario resolves to
    # both endpoints of relationship r1.
    task_competency_node = next(c for c in pillar_node.children if c.id == "Task Sequencing")
    task_scenario_node = task_competency_node.children[0].children[0]
    task_ko_ids = {child.id for child in task_scenario_node.children}
    assert task_ko_ids == {"p1", "t1"}


def test_traceability_drill_finds_subtree_by_level_and_id(db_session, not_ready_readiness_id):
    data = ExplanationDataLayer(db_session).build(not_ready_readiness_id)
    service = TraceabilityService(db_session)

    found = service.drill(data, "pillar", "OE")
    assert found is not None
    assert found.level == "pillar"
    assert found.id == "OE"

    missing = service.drill(data, "pillar", "does-not-exist")
    assert missing is None


# ---------------------------------------------------------------------------
# 6. End-to-end ExplanationEngine.explain()
# ---------------------------------------------------------------------------

def test_explanation_engine_end_to_end(db_session, not_ready_readiness_id):
    engine = ExplanationEngine(db_session, claude_client=ClaudeClient())
    result = engine.explain(not_ready_readiness_id)

    assert isinstance(result, ExplanationResult)
    assert result.data.readiness_decision == "Not Ready"
    assert result.template.decision_sentence.startswith("Receiver is NOT READY")
    assert isinstance(result.contextual, ContextualNarrative)
    assert result.contextual.text  # never empty -- template fallback guarantees this
    assert result.traceability.level == "readiness"
