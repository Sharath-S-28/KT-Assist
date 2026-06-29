"""
services/datasets/dataset_validator.py — Phase 13 dataset tuning/
verification harness.

This is the harness the Phase 13 spec's §1 "engineered backwards"
method depends on: every coverage/score number a dataset's ground-truth
files claim is *measured* by actually running the real, already-built
pipeline (services.kttl + services.coverage_engine + services.
gap_detection for extraction/coverage; services.graph_update for gap
closure; services.kase_scoring + services.threshold_model, via
WorkflowRunner, for golden scores) -- never hand-computed and asserted
as if it were fact. Always runs in DEV_MODE (no live API spend, fully
deterministic), per the spec's own "always runs in DEV_MODE for
determinism" instruction.

Boundary: this module orchestrates real services to *measure* outcomes
for dataset authoring/regression purposes. It contains no scoring logic
of its own -- every number it returns came from a real, already-tested
service call.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from sqlalchemy.orm import Session

import config
from models.ground_truth_models import GoldenResponse
from services.claude_client import ClaudeClient
from services.coverage_engine import compute_coverage
from services.datasets.dataset_loader import load_dataset
from services.graph_update import close_gap
from services.gap_detection import detect_gaps
from services.kttl import detect_package_template
from services.orchestration.workflow_runner import WorkflowRunner
from services.response_interpretation import InterpretationResult, InterpretedObjectChange


@dataclass
class ExtractionDiff:
    expected: dict[str, str]
    actual: dict[str, str]
    matches: bool
    mismatches: dict[str, tuple[str, str]] = field(default_factory=dict)  # type -> (expected, actual)


@dataclass
class CoverageCurveResult:
    initial_coverage: float
    step_coverages: list[float]
    final_coverage: float


@dataclass
class GoldenScoreResult:
    name: str
    ois_score: float
    decision: str
    certification_level: Optional[str]
    critical_gate_passed: bool
    competency_scores: dict[str, float]
    pillar_scores: dict[str, float]


class DatasetValidator:
    """Drives one dataset's assets/ground-truth through the real
    pipeline. Always DEV_MODE -- see module docstring."""

    def __init__(self, db: Session, claude_client: Optional[ClaudeClient] = None):
        self.db = db
        self.client = claude_client or ClaudeClient(dev_mode=True, cache_enabled=False)
        self.runner = WorkflowRunner(self.db, claude_client=self.client)

    @staticmethod
    def _boundary_mock_for(extraction_mock: dict[str, Any]) -> dict[str, Any]:
        """All-confirm boundary mock for every object the extraction_mock
        proposes -- the same pattern every prior phase's DEV_MODE test
        fixture uses (tests/level3/test_full_workflow.py, cli.py's demo)."""
        return {
            "verdicts": [
                {"object_id": obj["id"], "verdict": "confirm"}
                for obj in extraction_mock.get("objects", [])
            ]
        }

    def _type_status_map(self, package_id: str) -> dict[str, str]:
        """Per-type Complete/Partial/Missing for the package's current
        graph, via the real Template Intelligence Engine + Coverage
        Engine -- the same per-type unit ground_truth_models.py grounds
        itself in."""
        from services.graph_storage import load_graph_version

        payload = load_graph_version(self.db, package_id)
        template = detect_package_template(payload)
        coverage = compute_coverage(payload, template)
        return {object_type: tc.status for object_type, tc in coverage.per_type.items()}

    # -- D1/D4/D7: extraction shape ---------------------------------------

    def validate_extraction(self, dataset_name: str, package_id: str) -> ExtractionDiff:
        """Ingest the dataset's asset+extraction_mock for real, then diff
        the resulting per-type status against expected_objects.json's
        'initial' state."""
        ds = load_dataset(dataset_name)
        self.runner.ingest(
            package_id,
            ds["asset_filename"],
            ds["asset_content"],
            extraction_mock=ds["extraction_mock"],
            boundary_mocks=[self._boundary_mock_for(ds["extraction_mock"])],
            relationship_mock={"relationships": []},
        )

        expected = {
            entry["object_type"]: entry["status"]
            for entry in ds["expected_objects"]["initial"]["types"]
        }
        actual = self._type_status_map(package_id)

        mismatches = {
            t: (expected[t], actual.get(t, "<not in profile>"))
            for t in expected
            if actual.get(t) != expected[t]
        }
        return ExtractionDiff(expected=expected, actual=actual, matches=not mismatches, mismatches=mismatches)

    # -- D2/D3 (and D5/D6): the coverage curve -----------------------------

    def validate_coverage_curve(self, dataset_name: str, package_id: str) -> CoverageCurveResult:
        """Measure the real initial coverage, apply every gap_answers.json
        step via the real services.graph_update.close_gap, and measure
        coverage after each step. This is the actual tuning loop: run it,
        read the real numbers, adjust the ground-truth files, repeat."""
        ds = load_dataset(dataset_name)

        initial_kva = self.runner.validate(package_id)
        initial_coverage = initial_kva.coverage_score

        step_coverages: list[float] = []
        for step in ds["gap_answers"]["steps"]:
            interpretation = InterpretationResult(
                gap_object_type=step["object_type"],
                raw_text=step["description"],
                object_changes=[
                    InterpretedObjectChange(
                        action=step["action"],
                        object_type=step["object_type"],
                        name=step["name"],
                        description=step["description"],
                        target_object_id=step.get("target_object_id"),
                    )
                ],
            )
            update_result = close_gap(self.db, package_id, interpretation, claude_client=self.client)
            step_coverages.append(update_result.new_coverage_score)

        final_coverage = step_coverages[-1] if step_coverages else initial_coverage
        return CoverageCurveResult(
            initial_coverage=initial_coverage, step_coverages=step_coverages, final_coverage=final_coverage
        )

    # -- D8: golden assessment responses ------------------------------------

    # Deterministic detection-status bucketing -- the exact technique
    # tests/test_session28_kase_integration.py already proved produces
    # an unambiguous Pass-1/Pass-2 agreement (no arbitration, no
    # DEV_MODE heuristic ambiguity): one 5-significant-word marker per
    # competency, with a response text whose keyword-overlap ratio
    # lands squarely in one bucket (0.6 -> Demonstrated, 0.2 -> Partial,
    # 0.0 -> Missing).
    _MARKER_TEXT = "alpha bravo charlie delta echo"
    _RESPONSE_FOR = {
        "Demonstrated": "alpha bravo charlie report filed",  # 3/5 -> 0.6
        "Partial": "alpha report filed today",  # 1/5 -> 0.2
        "Missing": "report filed today nothing",  # 0/5 -> 0.0
    }

    def validate_golden_scores(
        self,
        package_id: str,
        participant_id: str,
        golden: GoldenResponse,
    ) -> GoldenScoreResult:
        """[PROPOSAL ruling, D8 scoring method]: D8's job is to pin down
        exact KASE/threshold/certification *regression* numbers across
        the full config.COMPETENCY_CATALOG, independent of which object
        types a given dataset's KTTL profile happens to expose. Routing
        golden responses through WorkflowRunner.generate_assessment
        against a real ingested package (as D1-D3's extraction/coverage
        validation correctly does) was tried first and rejected: KRA's
        scenario generation for the Power BI Dashboard profile only
        ever yields 3 coarse scenarios covering 6 of the 9 catalog
        competencies (Task Sequencing, Dependency Awareness, Control
        Application never appear, since no Dependency/Control object
        exists in that profile), and every scenario response status is
        applied at the whole-scenario granularity -- so the only
        achievable Critical-Gate-passing outcome in that graph is a
        clean sweep (OIS=100), making a "Conditionally Ready" golden
        example structurally unreachable there.

        D8 instead reuses test_session28_kase_integration.py's own
        proven technique directly: one synthetic Scenario (with one
        deterministic-bucket evidence marker) per competency in the
        full catalog, status-mapped by golden.competency_response_strategy
        (default "Demonstrated" for any competency not listed) -- the
        same construction Session 28's SET_A/SET_B already validated,
        generalized to whatever map a golden response wants. This still
        calls the real, unmodified services.kase.score_and_persist_readiness
        for every number returned; only the scenario *input* is
        synthetic, exactly as it already is in Session 28's own tests.

        Assumes the package has already cleared the Knowledge
        Sufficiency Gate elsewhere (D1-D3's job); a fresh
        sufficiency_gate_passed=True CoverageResult is built here since
        D8 is testing KASE scoring, not coverage."""
        import json

        from models import AssessmentPackage
        from models import Scenario as ScenarioRow
        from models import ScenarioResponse
        from models.asset import KnowledgeGraphVersion
        from models.coverage import CoverageResult

        latest_graph_version = (
            self.db.query(KnowledgeGraphVersion)
            .filter_by(package_id=package_id)
            .order_by(KnowledgeGraphVersion.version_number.desc())
            .first()
        )
        assessment_package = AssessmentPackage(
            package_id=package_id, graph_version_id=latest_graph_version.id, status="Validated"
        )
        self.db.add(assessment_package)
        self.db.flush()

        pairs = []
        for competency_name in config.COMPETENCY_CATALOG:
            status = golden.competency_response_strategy.get(competency_name, "Demonstrated")
            scenario = ScenarioRow(
                assessment_package_id=assessment_package.id,
                category="Operational",
                difficulty="L2",
                situation=f"Golden scenario for {competency_name}",
                expected_evidence_json=json.dumps([self._MARKER_TEXT]),
                competency_mapping_json=json.dumps([competency_name]),
                validation_status="Passed",
            )
            self.db.add(scenario)
            self.db.flush()
            response = ScenarioResponse(
                scenario_id=scenario.id,
                participant_id=participant_id,
                response_text=self._RESPONSE_FOR[status],
            )
            self.db.add(response)
            self.db.flush()
            pairs.append((scenario, response))

        coverage_result = CoverageResult(
            package_id=package_id,
            graph_version_id=latest_graph_version.id,
            coverage_score=1.0,
            sufficiency_gate_passed=True,
        )
        self.db.add(coverage_result)
        self.db.flush()

        rollup = self.runner.score_readiness(
            package_id, participant_id, golden.role_tier, pairs, gaps=[], coverage_result=coverage_result,
        )
        return GoldenScoreResult(
            name=golden.name,
            ois_score=rollup.scoring_result.ois_score,
            decision=rollup.threshold_resolution.decision,
            certification_level=rollup.threshold_resolution.certification_level,
            critical_gate_passed=rollup.threshold_resolution.critical_gate_passed,
            competency_scores=rollup.scoring_result.competency_scores,
            pillar_scores=rollup.scoring_result.pillar_scores,
        )
