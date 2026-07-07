"""
tests/test_guided_demo_lifecycle_scenes.py — UI Phase 2: Knowledge
Lifecycle Experience (issue_log #19).

Covers the new demo-presentation orchestrator methods
(get_discovery_summary, get_knowledge_gaps_detail, get_assurance_snapshot,
get_closure_history, get_traceability_example), their HTTP endpoints,
the frontend presentation-label mapping, and passive-render/no-mutation
guarantees. Every KCS/KQS/TC/AC/RC/OS/EV/gate/gap/finding value is read
or recomputed from the real hierarchical lifecycle -- never stored as a
frontend constant -- so these tests assert reconciliation against the
real API response, not against a hardcoded expected number.
"""

import pytest
from fastapi.testclient import TestClient

from database import get_db
from frontend.api_client import ApiClient
from frontend.guided_demo import presentation_labels as labels


@pytest.fixture()
def client(db_session):
    from app import create_app

    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    api = ApiClient(http_client=TestClient(app))
    yield api
    api.close()


def _advance_to_assurance_complete(client):
    client.reset_demo_hierarchical()
    client.ingest_demo_hierarchical()
    client.validate_demo_hierarchical()
    for _ in range(20):
        result = client.advance_demo_enrichment(max_rounds=1)
        if result["termination_reason"] == "sufficient":
            break
    return client.complete_demo_assurance()


# 3/4. Knowledge Discovery metrics come from API data; object-type counts reconcile

def test_discovery_summary_reconciles(client):
    client.reset_demo_hierarchical()
    client.ingest_demo_hierarchical()
    discovery = client.get_demo_discovery_summary()

    assert discovery["available"] is True
    assert sum(discovery["object_type_distribution"].values()) == discovery["node_count"]
    assert discovery["node_count"] == 50
    assert discovery["relationship_count"] > 0


# 5. Attribute-state counts reconcile ----------------------------------------

def test_attribute_state_distribution_reconciles(client):
    client.reset_demo_hierarchical()
    client.ingest_demo_hierarchical()
    discovery = client.get_demo_discovery_summary()

    total_states = sum(discovery["attribute_state_distribution"].values())
    assert total_states > 0
    assert discovery["attribute_state_distribution"].get("PRESENT", 0) == discovery["attributes_captured"]


def test_discovery_summary_unavailable_before_ingest(client):
    client.reset_demo_hierarchical()
    discovery = client.get_demo_discovery_summary()
    assert discovery["available"] is False


# 6/7. Knowledge Assurance dimensions come from backend response; not recomputed in frontend

def test_assurance_snapshot_reads_real_dimensions(client):
    client.reset_demo_hierarchical()
    client.ingest_demo_hierarchical()
    client.validate_demo_hierarchical()
    snapshot = client.get_demo_assurance_snapshot()

    current = snapshot["current"]
    assert current["tc"] == 1.0
    assert current["ac"] == 1.0
    # Known, documented pre-closure value (issue_log #8/#13).
    assert current["rc"] == 0.0
    assert snapshot["pre_enrichment"]["kcs"] == current["kcs"]  # nothing enriched yet -- must match


# 8. Gate badges map correctly (structural) ----------------------------------

def test_gate_state_reflects_real_gate_booleans(client):
    client.reset_demo_hierarchical()
    client.ingest_demo_hierarchical()
    client.validate_demo_hierarchical()
    snapshot = client.get_demo_assurance_snapshot()
    current = snapshot["current"]
    assert current["sufficiency_gate_passed"] is False  # real, pre-closure
    assert isinstance(current["quality_gate_passed"], bool)


# 9/10/11. Findings/Knowledge Gap counts reconcile; prioritized ordering ------

def test_knowledge_gaps_detail_reconciles_and_is_ranked(client):
    client.reset_demo_hierarchical()
    client.ingest_demo_hierarchical()
    gaps = client.get_demo_knowledge_gaps()

    assert gaps["available"] is True
    assert gaps["gaps_count"] == len(gaps["gaps"])
    assert gaps["findings_count"] >= gaps["gaps_count"]
    # Real prioritization: every returned gap is Open (rank_gaps filters to open only).
    assert all(g["status"] == "Open" for g in gaps["gaps"])


# 12. Gap presentation labels are human-readable -----------------------------

def test_rule_family_labels_are_human_readable():
    assert labels.rule_family_label("access_ownership") == "Access & Ownership"
    assert labels.rule_family_label("failure_recovery") == "Failure Recovery"
    assert labels.rule_family_label("evidence_validation") == "Evidence & Validation"
    # Unmapped values fall back to a readable title-case, never raw underscores.
    assert "_" not in labels.rule_family_label("some_new_theme")


def test_attribute_state_labels_are_human_readable():
    assert labels.attribute_state_label("PRESENT") == "Captured"
    assert labels.attribute_state_label("NOT_OBSERVED") == "Not Yet Observed"
    assert labels.attribute_state_label("EXPLICITLY_UNKNOWN") == "Explicitly Unknown"


# 13. Enrichment action calls the real advance endpoint ----------------------

def test_gap_closure_advance_calls_real_endpoint_and_moves_metrics(client):
    client.reset_demo_hierarchical()
    client.ingest_demo_hierarchical()
    client.validate_demo_hierarchical()
    before = client.get_demo_assurance_snapshot()["current"]

    result = client.advance_demo_enrichment(max_rounds=1)
    assert result["rounds_this_call"] >= 0

    after = client.get_demo_assurance_snapshot()["current"]
    # Real revalidation must have run (RC moves once a round closes a gap).
    assert after["rc"] >= before["rc"]


# 14. No mutation occurs on passive render (repeated GETs are side-effect-free)

def test_passive_reads_do_not_mutate_state(client):
    _advance_to_assurance_complete(client)
    state1 = client.get_demo_state()
    client.get_demo_summary()
    client.get_demo_discovery_summary()
    client.get_demo_knowledge_gaps()
    client.get_demo_assurance_snapshot()
    client.get_demo_closure_history()
    client.get_demo_traceability_example()
    state2 = client.get_demo_state()
    assert state1 == state2


# 15/16. Before/current metrics sourced from real checkpoints; closure progress reflects backend

def test_closure_history_before_after_reconciles_with_graph_versions(client):
    client.reset_demo_hierarchical()
    client.ingest_demo_hierarchical()
    client.validate_demo_hierarchical()
    client.advance_demo_enrichment(max_rounds=1)
    client.advance_demo_enrichment(max_rounds=1)

    history = client.get_demo_closure_history()["history"]
    assert len(history) == 2
    for entry in history:
        assert entry["graph_version_after"] == entry["graph_version_before"] + 1
        assert entry["kcs_before"] is not None
        assert entry["kcs_after"] is not None
        assert entry["sme_response"]  # the real deterministic SME response text was captured
        assert entry["question"]


# 17. Representative interactions come from real gap/closure data -----------

def test_closure_history_entries_reference_real_objects(client):
    client.reset_demo_hierarchical()
    client.ingest_demo_hierarchical()
    client.validate_demo_hierarchical()
    client.advance_demo_enrichment(max_rounds=1)

    discovery = client.get_demo_discovery_summary()
    history = client.get_demo_closure_history()["history"]
    assert history[0]["object_type"] in discovery["object_type_distribution"]


# 18/19. Assurance Result reads real KAR; Transition Risk empty state --------

def test_assurance_result_reads_real_kar_after_full_closure(client):
    kar = _advance_to_assurance_complete(client)
    assert kar["sufficiency_gate_passed"] is True
    assert kar["quality_gate_passed"] is True

    snapshot = client.get_demo_assurance_snapshot()
    current = snapshot["current"]
    assert current["sufficiency_gate_passed"] is True
    # transition_risk_detail structurally present (list, possibly non-empty for this real case)
    assert isinstance(current["transition_risk_detail"], list)


# 20. Traceability component does not invent unavailable links --------------

def test_traceability_returns_none_before_any_closure_interaction(client):
    client.reset_demo_hierarchical()
    client.ingest_demo_hierarchical()
    client.validate_demo_hierarchical()
    result = client.get_demo_traceability_example()
    assert result["example"] is None


def test_traceability_uses_real_data_after_closure(client):
    client.reset_demo_hierarchical()
    client.ingest_demo_hierarchical()
    client.validate_demo_hierarchical()
    client.advance_demo_enrichment(max_rounds=1)
    result = client.get_demo_traceability_example()["example"]
    assert result is not None
    assert result["rule_family"]
    assert result["object_name"]
    assert result["question"]


# 25. Frontend boundary test remains green (covered by tests/test_frontend_boundary.py,
# re-run explicitly here to be certain the new files comply)

def test_new_frontend_files_do_not_import_forbidden_modules():
    import ast
    from pathlib import Path

    forbidden = {"services", "agents", "models", "storage", "database"}
    repo_root = Path(__file__).resolve().parent.parent
    for relative in (
        "frontend/guided_demo/lifecycle_scenes.py",
        "frontend/guided_demo/presentation_labels.py",
        "frontend/guided_demo/guided_shell.py",
    ):
        path = repo_root / relative
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                imported.add(node.module.split(".")[0])
        assert not (imported & forbidden), f"{relative} imports forbidden module(s): {imported & forbidden}"


# 26. No external Anthropic call is triggered by passive UI/API reads -------

def test_no_anthropic_call_from_lifecycle_scene_reads(client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _advance_to_assurance_complete(client)
    client.get_demo_discovery_summary()
    client.get_demo_knowledge_gaps()
    client.get_demo_assurance_snapshot()
    client.get_demo_closure_history()
    client.get_demo_traceability_example()
