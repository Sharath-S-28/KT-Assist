"""
schemas/hierarchical.py — API Read Contracts for the Hierarchical Path
(Phase 4 / Wave 7, Hierarchical Knowledge Assurance redesign).

Additive only -- no existing schema in schemas/gap.py, schemas/dashboard.py,
etc. is touched. These back the new, additive
services/routers/hierarchical.py endpoints, reachable only for a
package that has opted in via KnowledgePackage.kttl_profile_id.
"""

from typing import Optional

from pydantic import BaseModel


class FindingRead(BaseModel):
    model_config = {"from_attributes": True}

    finding_id: str
    gap_type: str
    rule_source: str
    rule_family: str
    object_id: Optional[str]
    element: str
    description: str


class KnowledgeGapRead(BaseModel):
    model_config = {"from_attributes": True}

    gap_id: str
    object_id: Optional[str]
    rule_family: str
    findings: list[FindingRead]
    consolidated_question: str
    criticality: str
    risk_level: str
    blocking_readiness_gate: bool
    status: str


class TransitionRiskRead(BaseModel):
    model_config = {"from_attributes": True}

    risk_id: str
    risk_rule_id: str
    risk_rule_version: int
    operational_scenario: str
    description: str
    contributing_gap_ids: list[str]
    severity: str
    status: str
    traceability_ref: str


class KnowledgeAssuranceResultRead(BaseModel):
    package_id: str
    graph_version_id: str
    profile_id: str
    profile_version: int
    kcs: Optional[float]
    tc: Optional[float]
    ac: Optional[float]
    rc: Optional[float]
    kqs: Optional[float]
    os: Optional[float]
    ev: Optional[float]
    sufficiency_gate_passed: bool
    quality_gate_applicable: bool
    quality_gate_passed: Optional[bool]
    critical_unresolved_gaps: list[KnowledgeGapRead]
    transition_risks: list[TransitionRiskRead]


class ClosureStatusRead(BaseModel):
    """Read-only snapshot of where the package's hierarchical closure
    stands right now -- NOT a live/in-progress closure loop run (see
    services/routers/hierarchical.py's module docstring for why
    submitting an answer via HTTP is out of this wave's scope)."""

    package_id: str
    sufficient: bool
    open_gap_count: int
    ranked_open_gaps: list[KnowledgeGapRead]  # highest priority first
