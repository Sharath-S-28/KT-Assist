"""
tests/test_session19_graph_update.py — Phase 6 / Session 19 success
criterion: closing a gap raises coverage and produces a labelled new
graph version with a delta.

Worked example reused throughout (same Dashboard package as Sessions
15-17): Process Complete, Task Partial (empty description), System
Missing, Business Rule Complete, Risk Complete.
  weights: Process=3, Task=3, System=3, Business Rule=3, Risk=1 -> total=13
  v1 observed: Process(3) + Task(1.5) + Business Rule(3) + Risk(1) = 8.5
  v1 coverage_score = 8.5 / 13 = 0.6538461538461539

Step 1 -- close the System gap only (create a described System object):
  observed: 8.5 + 3 = 11.5 -> coverage = 11.5/13 = 0.8846153846153846
  Task is still Partial (required -> Critical criticality, Medium risk),
  so has_critical_gap stays True even though coverage now clears 0.85 --
  loop_terminated must stay False.

Step 2 -- also close the Task gap (update Task's description):
  observed: 11.5 - 1.5 + 3 = 13.0 -> coverage = 1.0, no gaps remain --
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
    """Process Complete, Task Partial, Business Rule Complete, Risk
    Complete, System missing entirely -- the now-familiar 8.5/13 graph."""
    nodes = [
        KnowledgeObject(id="p1", object_type="Process", name="Process", description="Closes the books monthly.", criticality="Important"),
        KnowledgeObject(id="t1", object_type="Task", name="Task", description="", criticality="Important"),
        KnowledgeObject(id="b1", object_type="Business Rule", name="Business Rule", description="GL must balance to zero.", criticality="Important"),
        KnowledgeObject(id="r1", object_type="Risk", name="Risk", description="Late close risk.", criticality="Important"),
    ]
    return save_graph_version(db_session, package_id, nodes, relationships=[])


def _system_closure_interpretation():
    return InterpretationResult(
        gap_object_type="System",
        raw_text="We use SAP FI to run the GL close.",
        object_changes=[
            InterpretedObjectChange(
                action="create", object_type="System", name="SAP FI",
                description="SAP FI is the system of record for the GL close.",
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

    result = close_gap(db_session, sample_package.id, _system_closure_interpretation())

    assert isinstance(result, GraphUpdateResult)
    assert result.previous_version == 1
    assert result.new_version == 2
    assert result.change_summary.startswith("Gap closure:")
    assert "System" in result.change_summary


def test_db_version_row_persists_the_change_summary(db_session, sample_package):
    _seed_worked_example_v1(db_session, sample_package.id)
    close_gap(db_session, sample_package.id, _system_closure_interpretation())

    versions = list_graph_versions(db_session, sample_package.id)
    assert [v.version_number for v in versions] == [1, 2]
    assert versions[0].change_summary is None
    assert versions[1].change_summary is not None
    assert "System" in versions[1].change_summary


# ---------------------------------------------------------------------------
# Coverage delta -- hand-verified worked example, step 1 (partial closure)
# ---------------------------------------------------------------------------

def test_closing_one_gap_raises_coverage_by_the_exact_expected_delta(db_session, sample_package):
    _seed_worked_example_v1(db_session, sample_package.id)

    result = close_gap(db_session, sample_package.id, _system_closure_interpretation())

    assert result.previous_coverage_score == pytest.approx(8.5 / 13)
    assert result.new_coverage_score == pytest.approx(11.5 / 13)
    assert result.coverage_delta == pytest.approx(3 / 13)
    assert result.coverage_delta > 0


def test_partial_closure_does_not_terminate_the_loop_due_to_remaining_critical_gap(db_session, sample_package):
    _seed_worked_example_v1(db_session, sample_package.id)

    result = close_gap(db_session, sample_package.id, _system_closure_interpretation())

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
    first = close_gap(db_session, sample_package.id, _system_closure_interpretation())
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
    assert second.previous_coverage_score == pytest.approx(11.5 / 13)
    assert second.new_coverage_score == pytest.approx(1.0)
    assert second.coverage_delta == pytest.approx(1.5 / 13)
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
