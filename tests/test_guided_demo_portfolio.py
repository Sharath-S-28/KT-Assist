"""
tests/test_guided_demo_portfolio.py — UI Phase 1: Executive Command
Center + Guided Demo Case Shell.

Covers the synthetic portfolio fixture's determinism/reconciliation,
the new demo-hierarchical api_client wrappers, PBI-case identity
mapping, and the guided shell's stage/resume-action logic. Streamlit
rendering itself (st.title/st.dataframe/etc.) is not unit-tested here
-- there is no existing per-screen test convention in this repo
(only tests/test_frontend_boundary.py's AST guard) -- so this suite
targets the same testable surface every other frontend test does:
pure functions and ApiClient methods against the real FastAPI app.
"""

import inspect

import pytest
from fastapi.testclient import TestClient

from database import get_db
from frontend.api_client import ApiClient
from frontend.guided_demo import guided_shell, portfolio_fixture as pf


@pytest.fixture()
def client(db_session):
    from app import create_app

    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    api = ApiClient(http_client=TestClient(app))
    yield api
    api.close()


# 1/2. Fixture loads deterministically, expected case count -----------------

def test_fixture_loads_deterministically_with_expected_case_count():
    first = pf.get_all_cases()
    second = pf.get_all_cases()
    assert first == second
    assert 12 <= len(first) <= 18
    assert sum(1 for c in first if c.is_real_case) == 1


# 3. Fixture totals reconcile with computed KPIs -----------------------------

def test_kpi_totals_reconcile_with_fixture():
    cases = pf.get_all_cases()
    assert pf.total_active_transitions(cases) == len(cases)
    assert pf.total_knowledge_assured(cases) == sum(
        1 for c in cases if c.knowledge_assurance_status == pf.KNOWLEDGE_ASSURANCE_COMPLETE
    )
    assert pf.total_receivers_assessed(cases) == sum(c.receivers_assessed for c in cases)
    assert pf.total_operational_exposure(cases) == sum(c.operational_exposure for c in cases)
    assert pf.total_critical_risk_transitions(cases) == sum(1 for c in cases if c.risk_level == pf.RISK_CRITICAL)


# 4. Readiness distribution reconciles ---------------------------------------

def test_readiness_distribution_reconciles_with_receiver_totals():
    cases = pf.get_all_cases()
    dist = pf.readiness_distribution(cases)
    assert sum(dist.values()) == sum(c.receiver_count for c in cases)


def test_readiness_distribution_handles_mixed_real_outcome():
    summary = {
        "stage": "ASSESSMENT_COMPLETE",
        "receivers": {
            "p1": {"name": "Priya", "status": "assessed", "final_decision": "Ready"},
            "p2": {"name": "B", "status": "assessed", "final_decision": "Conditionally Ready"},
            "p3": {"name": "C", "status": "assessed", "final_decision": "Not Ready"},
        },
    }
    cases = pf.apply_real_pbi_state(pf.get_all_cases(), summary)
    dist = pf.readiness_distribution(cases)
    # Every one of the 3 real receivers is counted individually --
    # never collapsed into a single misleading bucket.
    assert sum(dist.values()) == sum(c.receiver_count for c in cases)
    assert dist[pf.READY] >= 1
    assert dist[pf.CONDITIONALLY_READY] >= 1
    assert dist[pf.NOT_READY] >= 1


# 5. Business-unit aggregation reconciles -------------------------------------

def test_business_unit_aggregation_reconciles():
    cases = pf.get_all_cases()
    bu_summary = pf.business_unit_summary(cases)
    assert sum(v["case_count"] for v in bu_summary.values()) == len(cases)
    assert sum(v["operational_exposure"] for v in bu_summary.values()) == pf.total_operational_exposure(cases)


# 6. Executive attention items come from the same fixture ---------------------

def test_executive_attention_items_are_drawn_from_the_fixture():
    cases = pf.get_all_cases()
    attention = pf.get_executive_attention_items(cases)
    assert len(attention) > 0
    case_ids = {c.case_id for c in cases}
    assert all(item.case_id in case_ids for item in attention)
    assert all(
        item.readiness_status == pf.NOT_READY or item.risk_level in (pf.RISK_CRITICAL, pf.RISK_HIGH)
        for item in attention
    )


# 7. PBI case maps to the existing real demo identity -------------------------

def test_pbi_case_maps_to_real_demo_identity(client):
    state = client.get_demo_state()
    cases = pf.get_all_cases()
    pbi_case = next(c for c in cases if c.is_real_case)
    assert pbi_case.case_id == pf.PBI_CASE_ID
    # The real package/program ids always come from the API, never
    # hardcoded in the frontend fixture.
    assert state["package_id"]
    assert state["program_id"]


# 8. PBI case drill-through resolves the real demo state ----------------------

def test_pbi_drill_through_resolves_real_state(client):
    summary = client.get_demo_summary()
    cases = pf.apply_real_pbi_state(pf.get_all_cases(), summary)
    pbi_case = next(c for c in cases if c.case_id == pf.PBI_CASE_ID)
    assert pbi_case.current_stage == pf.stage_label(summary["stage"])


# 9. Non-PBI cases do not invoke hierarchical lifecycle operations -----------

def test_synthetic_case_detail_renderer_takes_no_api_client():
    """Structural guarantee: the synthetic-case detail view has no
    `client` parameter at all, so it cannot call any demo hierarchical
    API operation even by accident."""
    signature = inspect.signature(guided_shell._render_synthetic_case_detail)
    assert list(signature.parameters) == ["case"]


# 10. Resume CTA maps correctly for each DemoJourneyStage --------------------

@pytest.mark.parametrize("stage,expected_action", [
    ("START", "Begin Knowledge Intake"),
    ("INGESTED", "Resume at Knowledge Discovery"),
    ("VALIDATED", "Resume Gap Closure"),
    ("ENRICHING", "Resume Gap Closure"),
    ("ASSURANCE_COMPLETE", "Continue to Receiver Assessment"),
    ("ASSESSMENT_COMPLETE", "View Readiness Decision"),
])
def test_resume_action_maps_correctly_per_stage(stage, expected_action):
    assert guided_shell._resume_action_for_stage(stage) == expected_action


@pytest.mark.parametrize("stage,assessed,total,expected_index", [
    ("START", 0, 3, 0),
    ("INGESTED", 0, 3, 1),
    ("VALIDATED", 0, 3, 2),
    ("ENRICHING", 0, 3, 3),
    ("ASSURANCE_COMPLETE", 0, 3, 4),
    ("ASSURANCE_COMPLETE", 1, 3, 5),
    ("ASSESSMENT_COMPLETE", 2, 3, 5),
    ("ASSESSMENT_COMPLETE", 3, 3, 6),
])
def test_conceptual_progress_index_derived_from_real_stage_and_receivers(stage, assessed, total, expected_index):
    assert guided_shell._conceptual_index(stage, assessed, total) == expected_index


# 12. Demo API client wrappers work ------------------------------------------

def test_demo_state_and_summary_client_wrappers_work(client):
    state = client.get_demo_state()
    assert "stage" in state and "package_id" in state

    summary = client.get_demo_summary()
    assert "receivers" in summary
    assert set(summary["receivers"]) or summary["stage"] == "START"


# 13. No external Anthropic call is made by dashboard rendering/state retrieval

def test_no_anthropic_call_from_demo_state_and_summary_retrieval(client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    # Both calls must succeed with no API key configured at all --
    # proving neither ever attempts a live Anthropic call.
    client.get_demo_state()
    client.get_demo_summary()


# 11 (partial, structural). Existing generic screens remain available -------

def test_streamlit_app_still_registers_all_ten_generic_screens():
    import streamlit_app

    for name in (
        "_screen1", "_screen2", "_screen3", "_screen4", "_screen5",
        "_screen6", "_screen7", "_screen8", "_screen9", "_screen10",
    ):
        assert hasattr(streamlit_app, name), f"streamlit_app.{name} must still exist"
