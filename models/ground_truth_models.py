"""
models/ground_truth_models.py — Phase 13 (Synthetic Dataset Engineering)
shared schema.

[PROPOSAL ruling -- type-level, not object-instance-level, ground truth]:
the Phase 13 spec's own §2.1 sketch models ground truth as a list of
individually-weighted GTObject instances (criticality "critical" /
"important" / "supporting", weight 3/2/1 each). That does not match how
the real, already-built Coverage Engine (services/coverage_engine.py,
Session 15) actually scores a package: coverage is computed per
*expected object TYPE* (Process, Task, System, ...), not per object
instance. A type's weight is binary-derived from whether the type is in
the template's `required` set (config.CRITICALITY_WEIGHTS["Critical"])
or `optional` set (config.CRITICALITY_WEIGHTS["Supporting"]) — there is
no per-instance "Important" tier in the real scoring math, and adding a
second instance of an already-Complete type changes nothing. Modeling
ground truth at the object-instance level would let an author believe
they'd engineered a precise score that the real engine would simply
never produce. This module instead mirrors services/coverage_engine.py's
actual unit of scoring: one entry per *expected type*, carrying the
Complete/Partial/Missing status that type's instances need to produce.

[PROPOSAL ruling -- KTTL profiles are whatever config.py says, not the
spec's frozen profile text]: the Phase 13 spec's §0 grounding quotes
Dashboard/Python Application/Operations required-object lists that
diverge from the real, already-built and already-tested
config.KNOWLEDGE_TYPE_TEMPLATES (Session 14) -- e.g. the spec's
Dashboard profile requires Escalation/Dependency/Control and treats
Business Rule as absent, while the real implemented profile requires
Process/Task/System/Business Rule with Risk optional (no Escalation,
Dependency, or Control in the Dashboard profile at all). Per the
project's standing rule ("ground in the real codebase, don't invent
vocabulary" — see services/demo/demo_runner.py's decision/certification
ruling), every dataset built against this schema targets the REAL
config.KNOWLEDGE_TYPE_TEMPLATES profile for its package_type, never the
spec's illustrative text. The spec's "missing escalation/control/
dependency" framing is preserved only as a design *flavor* (intentional
gaps in safety-relevant content), not as literal required-object names
for Dataset 1's Dashboard profile.

[PROPOSAL ruling -- competency/evidence vocabulary]: similarly, the
spec's D8 section references a frozen "Exception Handling" competency
and marker IDs ("EH-03/04/06") that do not exist anywhere in the real,
already-built config.COMPETENCY_CATALOG (Session 21) or evidence-marker
pipeline (services/evidence_detection.py, Session 25) -- there is no
fixed, globally-numbered marker catalog in this codebase at all;
markers are generated per-scenario by KRA. D8's golden responses
therefore target real competency names from config.COMPETENCY_CATALOG
and drive them via the same `competency_response_strategy` mechanism
WorkflowRunner.build_scenario_responses already uses (Session 35/36),
never a fabricated marker-ID catalog. The Chunk 6 "critical competency
below 70 -> Not Ready" *shape* is reproduced faithfully; the specific
competency name is not.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

import config

Status = Literal["Complete", "Partial", "Missing"]


class ExpectedTypeStatus(BaseModel):
    """One expected object type's ground-truth status for one dataset
    state (initial or post-enrichment). `weight` and `required` are not
    author-supplied -- they are always re-derived from the real
    config.KNOWLEDGE_TYPE_TEMPLATES profile by GroundTruthGraph, so a
    ground-truth file can never silently drift from the engine's own
    weighting rule."""

    object_type: str
    status: Status


class GroundTruthGraph(BaseModel):
    """The complete ground-truth definition for one dataset state. Not
    itself the denominator -- the denominator (expected_weighted_total)
    is always whatever services.kttl + services.coverage_engine report
    for this package_type, recomputed live by DatasetValidator, never
    hand-computed here (see module docstring's "engine-authoritative"
    principle)."""

    package_type: str  # must be a key in config.KNOWLEDGE_TYPE_TEMPLATES
    types: list[ExpectedTypeStatus]

    def required_types(self) -> list[str]:
        return list(config.KNOWLEDGE_TYPE_TEMPLATES[self.package_type]["required"])

    def optional_types(self) -> list[str]:
        return list(config.KNOWLEDGE_TYPE_TEMPLATES[self.package_type]["optional"])

    def expected_weighted_total(self) -> float:
        template = config.KNOWLEDGE_TYPE_TEMPLATES[self.package_type]
        crit = config.CRITICALITY_WEIGHTS["Critical"]
        supp = config.CRITICALITY_WEIGHTS["Supporting"]
        return len(template["required"]) * crit + len(template["optional"]) * supp

    def expected_observed_points(self) -> float:
        """The points this state's statuses would produce, computed with
        the exact same per-type weight rule coverage_engine.py uses.
        This is a *prediction* for authoring purposes — DatasetValidator
        always re-measures the real value via the real engine and that
        measured value is what ground-truth files record as fact."""
        template = config.KNOWLEDGE_TYPE_TEMPLATES[self.package_type]
        required = set(template["required"])
        crit = config.CRITICALITY_WEIGHTS["Critical"]
        supp = config.CRITICALITY_WEIGHTS["Supporting"]
        total = 0.0
        for entry in self.types:
            weight = crit if entry.object_type in required else supp
            total += config.OBJECT_VALIDATION_SCORES[entry.status] * weight
        return total


class IntentionalGapProfile(BaseModel):
    """D2 / D5 / D7: the initial, gapped state of a dataset, plus the
    *measured* (engine-authoritative) coverage it produces. expected_*
    fields are filled in by DatasetValidator after a real KVA run
    against the real extraction_mock — never hand-asserted before the
    engine has actually reported them, per the spec's own "the
    authoritative coverage numbers are whatever the real Phase 5 engine
    reports" rule."""

    graph: GroundTruthGraph
    measured_initial_coverage: float
    coverage_tolerance: float = 0.02  # [PROPOSAL ruling -- §8: ±2 points, matching Phase 12's GOLDEN_TOLERANCE pattern


class GapAnswerStep(BaseModel):
    """One D3/D6 gap-answer script step: which gap object_type it
    targets, the InterpretedObjectChange-shaped payload to apply via
    services.graph_update.close_gap, and the measured coverage
    immediately after this step (filled in by DatasetValidator)."""

    object_type: str
    action: Literal["create", "update"]
    name: str
    description: str
    target_object_id: Optional[str] = None
    measured_coverage_after: Optional[float] = None


class CoverageCurve(BaseModel):
    """D3 / D6: the full omission -> restoration curve for one dataset,
    every number measured against the real engine."""

    initial: float
    final: float
    steps: list[GapAnswerStep]


class GoldenResponse(BaseModel):
    """D8: one golden assessment response, engineered backwards from a
    target readiness band. `competency_response_strategy` is fed
    directly into WorkflowRunner.build_scenario_responses (Sessions
    35/36's already-proven mechanism) — this is the real lever that
    drives real evidence-marker detection, not a fabricated marker
    catalog. `expected` is filled in only after a real KASE run, by
    DatasetValidator.validate_golden_scores."""

    name: str
    role_tier: str
    competency_response_strategy: dict[str, str]
    expected_decision: Optional[str] = None
    expected_certification_level: Optional[str] = None
    expected_ois_score: Optional[float] = None
    expected_critical_gate_passed: Optional[bool] = None
    expected_competency_scores: dict[str, float] = Field(default_factory=dict)
    expected_pillar_scores: dict[str, float] = Field(default_factory=dict)
    ois_tolerance: float = 1.5  # [PROPOSAL ruling -- §8: OIS is a continuous score; ±1.5 points
