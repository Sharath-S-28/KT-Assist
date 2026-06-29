"""
tests/test_session19_graph_update.py — Phase 6 / Session 19 success
criterion: closing a gap raises coverage and produces a labelled new
graph version with a delta.

[PROPOSAL ruling, KTTL Chunk 2 reconciliation]: the worked example below
was redesigned because the prior Dashboard-flavored 13-point example no
longer reflects the new KTTL profiles. The new package now cleanly
auto-detects as Python Application (required: Process/Task/System/
Dependency/Risk/Control/Business Rule, optional: Known Issue) --
verified via services.kttl.detect_package_template -- with Process,
System, Dependency, Risk, Business Rule, and Known Issue all Complete,
Task Partial (empty description), and Control Missing entirely.
  weights: 7 required types * 3 + 1 optional type * 1 -> total = 22
  v1 observed: Process(3) + Task(1.5) + System(3) + Dependency(3) +
    Risk(3) + Business Rule(3) + Known Issue(1) + Control(0) = 17.5
  v1 coverage_score = 17.5 / 22 = 0.7954545454545454

Step 1 -- close the Control gap only (create a described Control object):
  observed: 17.5 + 3 = 20.5 -> coverage = 20.5/22 = 0.9318181818181818
  Task is still Partial (required -> Critical criticality, Medium risk),
  so has_critical_gap stays True even though coverage now clears 0.85 --
  loop_terminated must stay False.

Step 2 -- also close the Task gap (update Task's description):
  observed: 20.5 - 1.5 + 3 = 22.0 -> coverage = 1.0, no gaps remain --
  loop_terminated must become True.
"""

import pytest

from services.gap_detection import GapCandidate
from services.graph_storage import list_graph_versions, save_graph_version
from services.graph_update import GraphUpdateResult, close_gap
from services.response_interpretation import (
    InterpretedObjectChange,
    InterpretedRelationshipChange,
    InterpretationResult,
)
from schemas.knowledge_graph import KnowledgeObject, Relationship
from utils.errors import ValidationFailedError


def _seed_worked_example_v1(db_session, package_id):
    """Process/System/Dependency/Risk/Business Rule/Known Issue Complete,
    Task Partial, Control missing entirely -- the now-familiar 17.5/22
    Python Application graph."""
    nodes = [
        KnowledgeObject(id="p1", object_type="Process", name="Process", description="Closes the books monthly.", criticality="Important"),
        KnowledgeObject(id="t1", object_type="Task", name="Task", description="", criticality="Important"),
        KnowledgeObject(id="s1", object_type="System", name="System", description="SAP FI is the system of record.", criticality="Important"),
        KnowledgeObject(id="d1", object_type="Dependency", name="Dependency", description="Upstream GL feed.", criticality="Important"),
        KnowledgeObject(id="r1", object_type="Risk", name="Risk", description="Late close risk.", criticality="Important"),
        KnowledgeObject(id="b1", object_type="Business Rule", name="Business Rule", description="GL must balance to zero.", criticality="Important"),
        KnowledgeObject(id="k1", object_type="Known Issue", name="Known Issue", description="Known late-feed lag.", criticality="Important"),
    ]
    return save_graph_version(db_session, package_id, nodes, relationships=[])


def _control_closure_interpretation():
    return InterpretationResult(
        gap_object_type="Control",
        raw_text="We run a month-end close checklist control.",
        object_changes=[
            InterpretedObjectChange(
                action="create", object_type="Control", name="Close Checklist",
                description="Month-end close checklist control.",
                criticality="Important",
            )
        ],
        relationship_changes=[],
    )


# ---------------------------------------------------------------------------
# Version increment + change summary
# ---------------------------------------------------------------------------

def test_close_gap_increments_version_and_produces_labelled_change_summary(db_session, sample_package):
    _seed_worked_example_v1(db_session, sample_package.id)

    result = close_gap(db_session, sample_package.id, _control_closure_interpretation())

    assert isinstance(result, GraphUpdateResult)
    assert result.previous_version == 1
    assert result.new_version == 2
    assert result.change_summary.startswith("Gap closure:")
    assert "Control" in result.change_summary


def test_db_version_row_persists_the_change_summary(db_session, sample_package):
    _seed_worked_example_v1(db_session, sample_package.id)
    close_gap(db_session, sample_package.id, _control_closure_interpretation())

    versions = list_graph_versions(db_session, sample_package.id)
    assert [v.version_number for v in versions] == [1, 2]
    assert versions[0].change_summary is None
    assert versions[1].change_summary is not None
    assert "Control" in versions[1].change_summary


# ---------------------------------------------------------------------------
# Coverage delta -- hand-verified worked example, step 1 (partial closure)
# ---------------------------------------------------------------------------

def test_closing_one_gap_raises_coverage_by_the_exact_expected_delta(db_session, sample_package):
    _seed_worked_example_v1(db_session, sample_package.id)

    result = close_gap(db_session, sample_package.id, _control_closure_interpretation())

    assert result.previous_coverage_score == pytest.approx(17.5 / 22)
    assert result.new_coverage_score == pytest.approx(20.5 / 22)
    assert result.coverage_delta == pytest.approx(3 / 22)
    assert result.coverage_delta > 0


def test_partial_closure_does_not_terminate_the_loop_due_to_remaining_critical_gap(db_session, sample_package):
    _seed_worked_example_v1(db_session, sample_package.id)

    result = close_gap(db_session, sample_package.id, _control_closure_interpretation())

    # Coverage now clears 0.85, but Task is still Partial/Critical -- the
    # gate must still fail, and must agree exactly with KVAResult.is_sufficient.
    assert result.new_coverage_score >= 0.85
    assert result.kva_result.gap_summary["has_critical_gap"] is True
    assert result.loop_terminated is False
    assert result.loop_terminated == result.kva_result.is_sufficient


# ---------------------------------------------------------------------------
# Coverage delta -- step 2 (full closure, on top of step 1)
# ---------------------------------------------------------------------------

def test_fully_closing_remaining_gap_terminates_the_loop(db_session, sample_package):
    _seed_worked_example_v1(db_session, sample_package.id)
    first = close_gap(db_session, sample_package.id, _control_closure_interpretation())
    assert first.loop_terminated is False

    # The Task node's id is stable across versions ("t1" from the seed) --
    # target it directly with an "update" change.
    task_interpretation = InterpretationResult(
        gap_object_type="Task",
        raw_text="We reconcile sub-ledgers daily before the close.",
        object_changes=[
            InterpretedObjectChange(
                action="update", object_type="Task", name="Task",
                description="We reconcile sub-ledgers daily before the close.",
                criticality="Important", target_object_id="t1",
            )
        ],
        relationship_changes=[],
    )

    second = close_gap(db_session, sample_package.id, task_interpretation)

    assert second.previous_version == 2
    assert second.new_version == 3
    assert second.previous_coverage_score == pytest.approx(20.5 / 22)
    assert second.new_coverage_score == pytest.approx(1.0)
    assert second.coverage_delta == pytest.approx(1.5 / 22)
    assert second.kva_result.gaps == []
    assert second.loop_terminated is True
    assert second.loop_terminated == second.kva_result.is_sufficient


# ---------------------------------------------------------------------------
# Relationship maintenance
# ---------------------------------------------------------------------------

def test_existing_relationships_are_preserved_and_new_ones_are_appended(db_session, sample_package):
    nodes = [
        KnowledgeObject(id="t1", object_type="Task", name="Reconcile", description="Reconcile sub-ledgers.", criticality="Important"),
        KnowledgeObject(id="s1", object_type="System", name="SAP FI", description="GL system.", criticality="Important"),
    ]
    existing_rel = Relationship(id="rel-1", relationship_type="USES_SYSTEM", source_id="t1", target_id="s1")
    save_graph_version(db_session, sample_package.id, nodes, relationships=[existing_rel])

    interpretation = InterpretationResult(
        gap_object_type="Risk",
        raw_text="There is a risk of late close if reconciliation slips.",
        object_changes=[
            InterpretedObjectChange(
                action="create", object_type="Risk", name="Late close risk",
                description="Reconciliation slipping causes a late close.",
                criticality="Important",
            )
        ],
        relationship_changes=[
            InterpretedRelationshipChange(
                action="create", relationship_type="HAS_RISK",
                source_name="Reconcile", target_name="Late close risk",
            )
        ],
    )

    result = close_gap(db_session, sample_package.id, interpretation)

    from services.graph_storage import load_graph_version
    new_payload = load_graph_version(db_session, sample_package.id)

    assert new_payload.version == 2
    rel_types = {(r.relationship_type, r.source_id) for r in new_payload.relationships}
    # the original USES_SYSTEM edge survives untouched
    assert ("USES_SYSTEM", "t1") in rel_types
    # a new HAS_RISK edge was appended, resolved from the new Risk object's id
    has_risk = [r for r in new_payload.relationships if r.relationship_type == "HAS_RISK"]
    assert len(has_risk) == 1
    assert has_risk[0].source_id == "t1"
    new_risk_node = next(n for n in new_payload.nodes if n.name == "Late close risk")
    assert has_risk[0].target_id == new_risk_node.id
    assert "added 1 relationship(s)" in result.change_summary


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

def test_update_action_with_unknown_target_object_id_raises(db_session, sample_package):
    _seed_worked_example_v1(db_session, sample_package.id)
    bad_interpretation = InterpretationResult(
        gap_object_type="Task",
        raw_text="x",
        object_changes=[
            InterpretedObjectChange(
                action="update", object_type="Task", name="Task",
                description="x", target_object_id="does-not-exist",
            )
        ],
    )
    with pytest.raises(ValidationFailedError):
        close_gap(db_session, sample_package.id, bad_interpretation)


def test_relationship_change_with_unknown_object_name_raises(db_session, sample_package):
    _seed_worked_example_v1(db_session, sample_package.id)
    bad_interpretation = InterpretationResult(
        gap_object_type="System",
        raw_text="x",
        object_changes=[
            InterpretedObjectChange(
                action="create", object_type="System", name="SAP FI",
                description="x",
            )
        ],
        relationship_changes=[
            InterpretedRelationshipChange(
                action="create", relationship_type="USES_SYSTEM",
                source_name="No Such Task", target_name="SAP FI",
            )
        ],
    )
    with pytest.raises(ValidationFailedError):
        close_gap(db_session, sample_package.id, bad_interpretation)
