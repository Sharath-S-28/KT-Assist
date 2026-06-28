"""
tests/test_session24_kra_integration.py — Phase 7 / Session 24 success
criterion: a validated, pillar-complete assessment package is produced
from a graph and is reproducible; closes Phase 7 (Graph -> Assessment
Package end-to-end, scenarios pass four-layer validation, scenario
packages are cached by graph version).
"""

import pytest

import config
from models import AssessmentPackage, Scenario as ScenarioRow
from services.graph_storage import save_graph_version
from services.knowledge_model import validate_object, validate_relationship
from services.kra import (
    compose_assessment_package,
    compose_assessment_package_for_package,
    persist_assessment_package,
)
from services.scenario_cache import load_scenario_package_cache


@pytest.fixture(autouse=True)
def _isolated_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "GRAPH_STORAGE_DIR", tmp_path / "graphs")
    monkeypatch.setattr(config, "SCENARIO_CACHE_DIR", tmp_path / "scenario_cache")


def _full_sample_objects():
    return [
        validate_object({"id": "p1", "object_type": "Process", "name": "Month-End Close", "criticality": "Critical"}),
        validate_object({"id": "t1", "object_type": "Task", "name": "Reconcile Sub-Ledgers", "criticality": "Critical"}),
        validate_object({"id": "s1", "object_type": "System", "name": "SAP FI", "criticality": "Important"}),
        validate_object({"id": "d1", "object_type": "Dependency", "name": "Upstream Feed", "criticality": "Important"}),
        validate_object({"id": "b1", "object_type": "Business Rule", "name": "GL Balance Rule", "criticality": "Important"}),
        validate_object({"id": "r1", "object_type": "Risk", "name": "Late Close Risk", "criticality": "Critical"}),
        validate_object({"id": "c1", "object_type": "Control", "name": "Four-Eyes Review", "criticality": "Important"}),
        validate_object({"id": "e1", "object_type": "Escalation", "name": "Controller Escalation", "criticality": "Important"}),
        validate_object({"id": "k1", "object_type": "Known Issue", "name": "Duplicate Postings", "criticality": "Important"}),
    ]


def _full_sample_relationships():
    return [
        validate_relationship({"id": "rel-1", "relationship_type": "HAS_TASK", "source_id": "p1", "target_id": "t1"}),
        validate_relationship({"id": "rel-2", "relationship_type": "USES_SYSTEM", "source_id": "t1", "target_id": "s1"}),
        validate_relationship({"id": "rel-3", "relationship_type": "DEPENDS_ON", "source_id": "t1", "target_id": "d1"}),
        validate_relationship({"id": "rel-4", "relationship_type": "GOVERNED_BY", "source_id": "t1", "target_id": "b1"}),
        validate_relationship({"id": "rel-5", "relationship_type": "HAS_RISK", "source_id": "t1", "target_id": "r1"}),
        validate_relationship({"id": "rel-6", "relationship_type": "MITIGATED_BY", "source_id": "r1", "target_id": "c1"}),
        validate_relationship({"id": "rel-7", "relationship_type": "ESCALATES_TO", "source_id": "t1", "target_id": "e1"}),
        validate_relationship({"id": "rel-8", "relationship_type": "HAS_KNOWN_ISSUE", "source_id": "t1", "target_id": "k1"}),
    ]


@pytest.fixture
def saved_graph(db_session, sample_package):
    version_row, payload = save_graph_version(
        db_session, sample_package.id, _full_sample_objects(), _full_sample_relationships()
    )
    return sample_package, version_row, payload


# ---------------------------------------------------------------------------
# compose_assessment_package — pure function, reproducibility
# ---------------------------------------------------------------------------

def test_compose_assessment_package_is_pillar_complete_for_the_full_sample_graph(saved_graph):
    _, _, payload = saved_graph
    package = compose_assessment_package(payload)

    assert package["is_pillar_complete"] is True
    assert set(package["pillar_coverage"].keys()) == set(config.OIS_WEIGHTS.keys())
    assert all(package["pillar_coverage"].values())
    assert package["critical_competencies_covered"] is True
    assert package["scenario_count"] > 0


def test_compose_assessment_package_is_reproducible_for_an_identical_payload(saved_graph):
    _, _, payload = saved_graph
    first = compose_assessment_package(payload)
    second = compose_assessment_package(payload)

    assert first["scenarios"] == second["scenarios"]
    assert first["category_distribution"] == second["category_distribution"]
    assert first["difficulty_distribution"] == second["difficulty_distribution"]
    assert first["pillar_coverage"] == second["pillar_coverage"]


def test_compose_assessment_package_reports_rejected_scenarios_distinctly():
    from schemas.graph import GraphPayload
    from schemas.knowledge_graph import KnowledgeObject

    # A single isolated node still produces a structurally valid scenario
    # (Layer 1-4 all pass for real templates) -- this asserts the
    # accepted/rejected split keys always exist, even when nothing is
    # actually rejected.
    payload = GraphPayload(
        graph_id="g-iso", package_id="pkg-iso", version=1,
        nodes=[KnowledgeObject(id="p1", object_type="Process", name="Solo Process", description="x", criticality="Important")],
        relationships=[],
    )
    package = compose_assessment_package(payload)
    assert "rejected_scenarios" in package
    assert package["rejected_count"] == len(package["rejected_scenarios"])
    assert package["is_pillar_complete"] is False  # one Process scenario can't cover all 4 pillars


# ---------------------------------------------------------------------------
# compose_assessment_package_for_package — DB + cache wiring
# ---------------------------------------------------------------------------

def test_compose_assessment_package_for_package_caches_by_graph_version(db_session, saved_graph):
    package, version_row, payload = saved_graph

    first_dict, first_hit = compose_assessment_package_for_package(db_session, package.id)
    assert first_hit is False

    cached = load_scenario_package_cache(package.id, version_row.version_number)
    assert cached is not None
    assert cached["scenario_count"] == first_dict["scenario_count"]

    second_dict, second_hit = compose_assessment_package_for_package(db_session, package.id)
    assert second_hit is True
    assert second_dict == first_dict


def test_compose_assessment_package_for_package_use_cache_false_bypasses_cache(db_session, saved_graph):
    package, version_row, _ = saved_graph

    built, hit = compose_assessment_package_for_package(db_session, package.id, use_cache=False)
    assert hit is False
    assert load_scenario_package_cache(package.id, version_row.version_number) is None


# ---------------------------------------------------------------------------
# persist_assessment_package — ORM round trip
# ---------------------------------------------------------------------------

def test_persist_assessment_package_writes_validated_status_for_pillar_complete_package(db_session, saved_graph):
    package, version_row, payload = saved_graph
    package_dict = compose_assessment_package(payload)

    row = persist_assessment_package(db_session, package_dict)

    assert isinstance(row, AssessmentPackage)
    assert row.package_id == package.id
    assert row.graph_version_id == version_row.id
    assert row.status == "Validated"

    persisted_scenarios = (
        db_session.query(ScenarioRow).filter_by(assessment_package_id=row.id).all()
    )
    assert len(persisted_scenarios) == package_dict["scenario_count"]
    assert all(s.validation_status == "Passed" for s in persisted_scenarios)
    assert all(s.situation for s in persisted_scenarios)


def test_persist_assessment_package_writes_rejected_status_when_nothing_accepted(db_session, saved_graph):
    package, version_row, payload = saved_graph
    package_dict = compose_assessment_package(payload)
    package_dict = dict(package_dict)
    package_dict["scenarios"] = []
    package_dict["scenario_count"] = 0

    row = persist_assessment_package(db_session, package_dict)
    assert row.status == "Rejected"

    persisted_scenarios = (
        db_session.query(ScenarioRow).filter_by(assessment_package_id=row.id).all()
    )
    assert len(persisted_scenarios) == 0


def test_persist_assessment_package_writes_draft_status_when_not_pillar_complete(db_session, saved_graph):
    package, version_row, payload = saved_graph
    package_dict = compose_assessment_package(payload)
    package_dict = dict(package_dict)
    package_dict["is_pillar_complete"] = False

    row = persist_assessment_package(db_session, package_dict)
    assert row.status == "Draft"


def test_persist_assessment_package_round_trips_competency_mapping_json(db_session, saved_graph):
    import json

    package, version_row, payload = saved_graph
    package_dict = compose_assessment_package(payload)

    row = persist_assessment_package(db_session, package_dict)
    persisted_scenarios = (
        db_session.query(ScenarioRow).filter_by(assessment_package_id=row.id).all()
    )
    for s in persisted_scenarios:
        mapping = json.loads(s.competency_mapping_json)
        assert isinstance(mapping, list)
        assert len(mapping) >= config.MIN_COMPETENCIES_PER_SCENARIO


# ---------------------------------------------------------------------------
# End-to-end: graph -> assessment package, full pipeline
# ---------------------------------------------------------------------------

def test_end_to_end_graph_to_persisted_assessment_package(db_session, saved_graph):
    package, version_row, _ = saved_graph

    package_dict, cache_hit = compose_assessment_package_for_package(db_session, package.id)
    assert cache_hit is False

    row = persist_assessment_package(db_session, package_dict)
    db_session.flush()

    assert row.status == "Validated"
    reloaded = db_session.query(AssessmentPackage).filter_by(id=row.id).first()
    assert reloaded is not None
    assert len(reloaded.scenarios) == package_dict["scenario_count"]
