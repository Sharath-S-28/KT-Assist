"""
frontend/guided_demo/portfolio_fixture.py — deterministic, committed
synthetic transition-portfolio data for the Executive Command Center
(UI Phase 1).

Everything in TRANSITION_CASES is static, hand-authored fixture data --
never generated at runtime, never randomized. Exactly one entry
(PBI_CASE_ID) represents the real, validated hierarchical demo case;
its readiness/stage/receiver fields are placeholders here and get
overlaid with the real, live backend state (via apply_real_pbi_state,
fed from ApiClient.get_demo_summary()) before rendering -- everything
else about that row (name, business unit, knowledge provider, receiver
names) mirrors the real demo identity so there is only ever one PBI
case identity, never a second invented one.

All aggregation (KPIs, readiness distribution, business-unit rollups,
executive attention selection) is computed from this single list, so
every number the Executive Command Center shows reconciles against the
same source -- no parallel/duplicated totals anywhere.

This module imports nothing beyond the Python standard library, so it
is exempt from (and trivially satisfies) the frontend/ boundary guard
(tests/test_frontend_boundary.py) same as every other module here.
"""

from dataclasses import dataclass, replace
from typing import Optional

# Readiness statuses. The first three mirror the real KRA decision
# vocabulary (services.readiness.threshold_model) exactly; the other
# two describe portfolio cases that haven't reached a KRA decision yet.
READY = "Ready"
CONDITIONALLY_READY = "Conditionally Ready"
NOT_READY = "Not Ready"
ASSESSMENT_PENDING = "Assessment Pending"
ASSURANCE_IN_PROGRESS = "Knowledge Assurance In Progress"

RECEIVER_OUTCOME_STATUSES = (READY, CONDITIONALLY_READY, NOT_READY)
ALL_READINESS_STATUSES = (READY, CONDITIONALLY_READY, NOT_READY, ASSESSMENT_PENDING, ASSURANCE_IN_PROGRESS)

RISK_LOW, RISK_MEDIUM, RISK_HIGH, RISK_CRITICAL = "Low", "Medium", "High", "Critical"

KNOWLEDGE_ASSURANCE_COMPLETE = "Complete"
KNOWLEDGE_ASSURANCE_IN_PROGRESS = "In Progress"
KNOWLEDGE_ASSURANCE_NOT_STARTED = "Not Started"

# The one real case. Identity (name/provider/receiver roster) mirrors
# services.demo.hierarchical_fixtures -- but this module never imports
# that (it lives under services/, off-limits to frontend/); instead the
# real package/participant ids are discovered at render time from
# ApiClient.get_demo_summary()'s own response, never hardcoded here.
PBI_CASE_ID = "pbi-regional-sales-dashboards"


@dataclass(frozen=True)
class TransitionCase:
    case_id: str
    transition_name: str
    business_unit: str
    knowledge_provider: str
    receiver_count: int
    receivers_assessed: int
    knowledge_assurance_status: str
    readiness_status: str
    risk_level: str
    operational_exposure: int
    current_stage: str
    is_real_case: bool = False


TRANSITION_CASES: tuple[TransitionCase, ...] = (
    TransitionCase(
        "sap-finance-close", "SAP S/4HANA Finance Close Automation", "Finance", "Meera Iyer",
        4, 4, KNOWLEDGE_ASSURANCE_COMPLETE, READY, RISK_LOW, 180_000, "Completed",
    ),
    TransitionCase(
        "supplier-onboarding", "Global Supplier Onboarding Playbook", "Supply Chain", "Daniel Osei",
        3, 3, KNOWLEDGE_ASSURANCE_COMPLETE, CONDITIONALLY_READY, RISK_MEDIUM, 420_000, "Receiver Assessment",
    ),
    TransitionCase(
        PBI_CASE_ID, "Power BI Regional Sales Dashboards", "Commercial Analytics", "Ravi Menon",
        3, 0, KNOWLEDGE_ASSURANCE_NOT_STARTED, ASSESSMENT_PENDING, RISK_MEDIUM, 310_000,
        "Knowledge Intake", is_real_case=True,
    ),
    TransitionCase(
        "procure-to-pay-exceptions", "Procure-to-Pay Exception Handling", "Procurement", "Fatima Al-Sayed",
        5, 5, KNOWLEDGE_ASSURANCE_COMPLETE, NOT_READY, RISK_HIGH, 560_000, "Gap Resolution",
    ),
    TransitionCase(
        "escalation-routing", "Customer Escalation Routing (Tier 2)", "Customer Service", "Owen Clarke",
        2, 2, KNOWLEDGE_ASSURANCE_COMPLETE, READY, RISK_LOW, 95_000, "Completed",
    ),
    TransitionCase(
        "network-incident-runbook", "Network Incident Runbook Transfer", "Technology Operations", "Priyanka Rao",
        4, 4, KNOWLEDGE_ASSURANCE_COMPLETE, CONDITIONALLY_READY, RISK_MEDIUM, 275_000, "Receiver Assessment",
    ),
    TransitionCase(
        "plant-maintenance-scheduling", "Plant Maintenance Scheduling KT", "Operations", "Carlos Fernandes",
        3, 0, KNOWLEDGE_ASSURANCE_COMPLETE, ASSESSMENT_PENDING, RISK_MEDIUM, 190_000, "Assessment",
    ),
    TransitionCase(
        "accounts-payable-recon", "Accounts Payable Reconciliation", "Finance", "Grace Whitfield",
        3, 0, KNOWLEDGE_ASSURANCE_IN_PROGRESS, ASSURANCE_IN_PROGRESS, RISK_MEDIUM, 145_000, "Gap Resolution",
    ),
    TransitionCase(
        "inbound-logistics-carriers", "Inbound Logistics Carrier Management", "Supply Chain", "Tunde Bakare",
        4, 4, KNOWLEDGE_ASSURANCE_COMPLETE, NOT_READY, RISK_CRITICAL, 650_000, "Gap Resolution",
    ),
    TransitionCase(
        "marketing-mix-model", "Marketing Mix Model Handover", "Commercial Analytics", "Elena Vasquez",
        2, 2, KNOWLEDGE_ASSURANCE_COMPLETE, READY, RISK_LOW, 120_000, "Completed",
    ),
    TransitionCase(
        "warehouse-slotting", "Warehouse Slotting Optimization", "Operations", "Noah Bergstrom",
        3, 0, KNOWLEDGE_ASSURANCE_COMPLETE, ASSESSMENT_PENDING, RISK_MEDIUM, 210_000, "Assessment",
    ),
    TransitionCase(
        "vendor-risk-workflow", "Vendor Risk Assessment Workflow", "Procurement", "Aditi Deshmukh",
        3, 3, KNOWLEDGE_ASSURANCE_COMPLETE, CONDITIONALLY_READY, RISK_HIGH, 380_000, "Receiver Assessment",
    ),
    TransitionCase(
        "ivr-self-service-script", "IVR Self-Service Script Transfer", "Customer Service", "Liam O'Connor",
        2, 0, KNOWLEDGE_ASSURANCE_IN_PROGRESS, ASSURANCE_IN_PROGRESS, RISK_LOW, 85_000, "Knowledge Discovery",
    ),
    TransitionCase(
        "cloud-cost-governance", "Cloud Cost Governance Runbook", "Technology Operations", "Wei Zhang",
        4, 4, KNOWLEDGE_ASSURANCE_COMPLETE, READY, RISK_MEDIUM, 230_000, "Completed",
    ),
    TransitionCase(
        "trade-promotion-forecast", "Trade Promotion Forecasting Model", "Commercial Analytics", "Sofia Marchetti",
        3, 0, KNOWLEDGE_ASSURANCE_IN_PROGRESS, ASSURANCE_IN_PROGRESS, RISK_HIGH, 410_000, "Knowledge Discovery",
    ),
)


def get_all_cases() -> list[TransitionCase]:
    """A fresh, deterministic copy of the fixture -- callers may freely
    replace the PBI row without mutating the module-level constant."""
    return list(TRANSITION_CASES)


# -- Real-PBI-case overlay ---------------------------------------------------

# Demo journey stage (models.demo_journey.DEMO_JOURNEY_STAGES) -> a
# human-readable "current stage" label for the portfolio table/detail
# view. Mirrors the real stage names exactly (never invented) --
# labels only, the stage NAME itself always comes from the API.
_STAGE_LABELS: dict[str, str] = {
    "START": "Knowledge Intake",
    "INGESTED": "Knowledge Discovery",
    "VALIDATED": "Knowledge Assurance",
    "ENRICHING": "Gap Resolution",
    "ASSURANCE_COMPLETE": "Receiver Assessment",
    "ASSESSMENT_COMPLETE": "Readiness Decision",
}


def stage_label(stage: str) -> str:
    return _STAGE_LABELS.get(stage, stage)


def apply_real_pbi_state(cases: list[TransitionCase], summary: Optional[dict]) -> list[TransitionCase]:
    """Overlay the real, live backend demo state (ApiClient.get_demo_summary())
    onto the PBI row. `summary` may be None (backend unreachable) --
    the static placeholder row is used as-is in that case, never a
    fabricated one.

    Readiness status: while any receiver is unassessed, reflects
    knowledge-assurance progress (Assessment Pending / Knowledge
    Assurance In Progress); once all three real receivers have been
    scored, the case is deliberately NOT collapsed into a single
    all-green status -- it shows "Mixed Readiness" precisely because
    the three real outcomes differ (Ready / Conditionally Ready / Not
    Ready), and the portfolio table's own readiness distribution
    counts each of the case's receivers individually rather than
    double-counting a composite label (see readiness_distribution())."""
    if summary is None:
        return cases

    stage = summary.get("stage", "START")
    receivers = summary.get("receivers", {})
    assessed = [r for r in receivers.values() if r.get("status") == "assessed"]
    receiver_count = len(receivers) or 3

    if stage == "ASSESSMENT_COMPLETE" and len(assessed) == receiver_count:
        decisions = {r["final_decision"] for r in assessed}
        readiness_status = decisions.pop() if len(decisions) == 1 else "Mixed Readiness"
        knowledge_assurance_status = KNOWLEDGE_ASSURANCE_COMPLETE
    elif stage in ("ASSURANCE_COMPLETE", "ASSESSMENT_COMPLETE"):
        readiness_status = ASSESSMENT_PENDING
        knowledge_assurance_status = KNOWLEDGE_ASSURANCE_COMPLETE
    elif stage in ("VALIDATED", "ENRICHING"):
        readiness_status = ASSURANCE_IN_PROGRESS
        knowledge_assurance_status = KNOWLEDGE_ASSURANCE_IN_PROGRESS
    else:
        readiness_status = ASSESSMENT_PENDING
        knowledge_assurance_status = KNOWLEDGE_ASSURANCE_NOT_STARTED

    updated = []
    for case in cases:
        if case.case_id == PBI_CASE_ID:
            case = replace(
                case,
                receivers_assessed=len(assessed),
                receiver_count=receiver_count,
                knowledge_assurance_status=knowledge_assurance_status,
                readiness_status=readiness_status,
                current_stage=stage_label(stage),
            )
        updated.append(case)
    return updated


def pbi_receiver_outcomes(summary: Optional[dict]) -> dict[str, dict]:
    """{participant_id: {"name", "status", "ois_score", "final_decision", ...}}
    straight from the real summary -- used by the guided shell's
    receiver-outcome display. Empty if summary is None or nothing has
    been assessed yet."""
    if summary is None:
        return {}
    return summary.get("receivers", {})


# -- Pure aggregation (every number the dashboard shows traces to these) ----

def total_active_transitions(cases: list[TransitionCase]) -> int:
    return len(cases)


def total_knowledge_assured(cases: list[TransitionCase]) -> int:
    return sum(1 for c in cases if c.knowledge_assurance_status == KNOWLEDGE_ASSURANCE_COMPLETE)


def total_receivers_assessed(cases: list[TransitionCase]) -> int:
    return sum(c.receivers_assessed for c in cases)


def total_operational_exposure(cases: list[TransitionCase]) -> int:
    return sum(c.operational_exposure for c in cases)


def total_critical_risk_transitions(cases: list[TransitionCase]) -> int:
    return sum(1 for c in cases if c.risk_level == RISK_CRITICAL)


def readiness_distribution(cases: list[TransitionCase]) -> dict[str, int]:
    """Receiver-level (not case-level) counts across the 3 real KRA
    decision buckets plus a Pending bucket -- so the one mixed-outcome
    PBI case contributes 1 receiver to each of its 3 real buckets
    instead of being force-fit into a single label, and the totals
    still reconcile exactly against total_receivers_assessed()."""
    distribution: dict[str, int] = {READY: 0, CONDITIONALLY_READY: 0, NOT_READY: 0, "Pending": 0}
    for case in cases:
        if case.readiness_status in RECEIVER_OUTCOME_STATUSES:
            distribution[case.readiness_status] += case.receivers_assessed
            distribution["Pending"] += case.receiver_count - case.receivers_assessed
        elif case.readiness_status == "Mixed Readiness":
            # Real, live PBI outcome: exactly the 3 validated receivers.
            distribution[READY] += 1
            distribution[CONDITIONALLY_READY] += 1
            distribution[NOT_READY] += 1
        else:
            distribution["Pending"] += case.receiver_count
    return distribution


def business_unit_summary(cases: list[TransitionCase]) -> dict[str, dict[str, int]]:
    summary: dict[str, dict[str, int]] = {}
    for case in cases:
        bucket = summary.setdefault(
            case.business_unit, {"case_count": 0, "operational_exposure": 0, "critical_risk_count": 0},
        )
        bucket["case_count"] += 1
        bucket["operational_exposure"] += case.operational_exposure
        if case.risk_level == RISK_CRITICAL:
            bucket["critical_risk_count"] += 1
    return summary


def assurance_status_distribution(cases: list[TransitionCase]) -> dict[str, int]:
    distribution: dict[str, int] = {}
    for case in cases:
        distribution[case.knowledge_assurance_status] = distribution.get(case.knowledge_assurance_status, 0) + 1
    return distribution


_RISK_SEVERITY_ORDER = {RISK_CRITICAL: 3, RISK_HIGH: 2, RISK_MEDIUM: 1, RISK_LOW: 0}


def get_executive_attention_items(cases: list[TransitionCase], top_n: int = 4) -> list[TransitionCase]:
    """Highest-priority cases: Not Ready or Critical/High risk first,
    ranked by risk severity then operational exposure, so the panel
    always surfaces genuine outliers from the same fixture -- never a
    separately-curated list."""
    candidates = [
        c for c in cases
        if c.readiness_status == NOT_READY or c.risk_level in (RISK_CRITICAL, RISK_HIGH)
    ]
    candidates.sort(
        key=lambda c: (_RISK_SEVERITY_ORDER.get(c.risk_level, 0), c.operational_exposure),
        reverse=True,
    )
    return candidates[:top_n]


def attention_reason(case: TransitionCase) -> str:
    if case.readiness_status == NOT_READY:
        return "Not Ready — critical competency gate failing"
    if case.risk_level == RISK_CRITICAL:
        return "Critical transition risk concentration"
    if case.risk_level == RISK_HIGH:
        return "Elevated transition risk"
    return "Requires executive review"


def attention_action(case: TransitionCase) -> str:
    if case.readiness_status == NOT_READY:
        return "Escalate remediation plan with knowledge provider"
    if case.knowledge_assurance_status != KNOWLEDGE_ASSURANCE_COMPLETE:
        return "Expedite knowledge assurance closure"
    return "Review receiver readiness plan"
