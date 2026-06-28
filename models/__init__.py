"""
models — ORM model package.

18 models across 7 files, covering the full domain: programs, packages,
participants, receiver roles, assets, graph versions, coverage, gaps,
waivers, retries, assessments, scenarios, responses, evidence, competency,
pillar, OIS, and receiver readiness.

Import every model module here so that Base.metadata sees all tables
before database.init_db() calls create_all().
"""

from models.program import KTProgram, KnowledgePackage
from models.participant import Participant, ReceiverRoleAssignment
from models.asset import KnowledgeAsset, KnowledgeGraphVersion
from models.coverage import CoverageResult, GapRecord, GapWaiver, RetryAttempt
from models.assessment import AssessmentPackage, Scenario, ScenarioResponse
from models.scoring import (
    EvidenceMarkerResult,
    CompetencyResult,
    PillarResult,
    OISResult,
)
from models.readiness import ReceiverReadiness
from models.workflow import WorkflowTransitionLog

__all__ = [
    "KTProgram",
    "KnowledgePackage",
    "Participant",
    "ReceiverRoleAssignment",
    "KnowledgeAsset",
    "KnowledgeGraphVersion",
    "CoverageResult",
    "GapRecord",
    "GapWaiver",
    "RetryAttempt",
    "AssessmentPackage",
    "Scenario",
    "ScenarioResponse",
    "EvidenceMarkerResult",
    "CompetencyResult",
    "PillarResult",
    "OISResult",
    "ReceiverReadiness",
    "WorkflowTransitionLog",
]
