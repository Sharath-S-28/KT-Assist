"""
services/kra.py — Assessment Package Composition & KRA Integration
(Phase 7 / KRA, Session 24). Closes Phase 7.

End-to-end pipeline wiring Sessions 21-23 together into one Knowledge
Readiness Agent (KRA) entry point:

    graph (GraphPayload)
      -> generate_scenarios_for_graph        (Session 21)
      -> build_weighted_scenario_set          (Session 22)
      -> validate_scenario_set                (Session 23)
      -> cached by graph version              (Session 23)
      -> compose_assessment_package           (this session)

compose_assessment_package() is a pure function of its GraphPayload (plus
optional claude_client/mock overrides for Layer 4): the same graph version
always produces the same package, which is what makes the package
reproducible and safe to cache.

A package is "pillar-complete" when every OIS pillar (config.OIS_WEIGHTS
keys: OE, CC, SA, GC) is represented by at least one competency among the
*accepted* (validated) scenarios -- not merely generated, since a
rejected scenario's competency mapping must not count toward coverage.

KRA boundary (non-negotiable, restated at the integration point where
it is most tempting to violate): this module composes and persists a
scenario package only. It must NOT calculate OIS, determine readiness,
or modify the knowledge graph -- those are KASE (Phase 8) and KGE
concerns respectively.
"""

import json
from dataclasses import asdict, dataclass, field
from typing import Optional

from sqlalchemy.orm import Session

import config
from models import AssessmentPackage, KnowledgeGraphVersion, Scenario as ScenarioRow
from schemas.graph import GraphPayload
from services.graph_storage import load_graph_version
from services.scenario_cache import get_or_build_scenario_package
from services.scenario_generation import generate_scenarios_for_graph
from services.scenario_validation import validate_scenario_set
from services.scenario_weighting import (
    build_weighted_scenario_set,
    compute_category_distribution,
    compute_difficulty_distribution,
)
from utils.errors import NotFoundError


def _pillar_coverage(competency_names: set[str]) -> dict[str, bool]:
    """For each OIS pillar (config.OIS_WEIGHTS), is at least one of the
    given competency names mapped to it (config.COMPETENCY_CATALOG)?"""
    coverage = {pillar: False for pillar in config.OIS_WEIGHTS}
    for name in competency_names:
        info = config.COMPETENCY_CATALOG.get(name)
        if info is not None:
            coverage[info["pillar"]] = True
    return coverage


def compose_assessment_package(
    payload: GraphPayload,
    claude_client=None,
    judgment_mock: Optional[dict] = None,
) -> dict:
    """Pure, deterministic function: GraphPayload -> a fully-composed,
    JSON-serializable assessment package dict. Calling this twice with
    an identical payload (and no claude_client/mock variance) always
    yields an identical result -- the reproducibility the success
    criterion requires."""
    generated = generate_scenarios_for_graph(payload)
    weighted = build_weighted_scenario_set(generated)
    accepted, rejected = validate_scenario_set(
        weighted, claude_client=claude_client, judgment_mock=judgment_mock
    )

    accepted_competencies: set[str] = set()
    for w in accepted:
        accepted_competencies.update(w.competency_mapping)

    pillar_coverage = _pillar_coverage(accepted_competencies)
    is_pillar_complete = all(pillar_coverage.values())

    critical_competencies = {
        name for name, info in config.COMPETENCY_CATALOG.items() if info["is_critical"]
    }
    critical_covered = critical_competencies <= accepted_competencies

    accepted_dicts = [
        {
            "source_id": w.scenario.source_id,
            "source_kind": w.scenario.source_kind,
            "type_label": w.scenario.type_label,
            "category": w.scenario.category,
            "difficulty": w.difficulty,
            "situation": w.scenario.situation,
            "context": w.scenario.context,
            "trigger": w.scenario.trigger,
            "decision_point": w.scenario.decision_point,
            "expected_evidence": list(w.scenario.expected_evidence),
            "competency_mapping": list(w.competency_mapping),
            "evidence_markers": [
                {"marker_text": m.marker_text, "max_score": m.max_score} for m in w.evidence_markers
            ],
            "validation_status": "Passed",
        }
        for w in accepted
    ]
    rejected_dicts = [
        {
            "source_id": w.scenario.source_id,
            "type_label": w.scenario.type_label,
            "rejection_reasons": result.rejection_reasons,
            "validation_status": "Rejected",
        }
        for w, result in rejected
    ]

    return {
        "package_id": payload.package_id,
        "graph_id": payload.graph_id,
        "graph_version": payload.version,
        "scenarios": accepted_dicts,
        "rejected_scenarios": rejected_dicts,
        "category_distribution": compute_category_distribution(accepted),
        "difficulty_distribution": compute_difficulty_distribution(accepted),
        "pillar_coverage": pillar_coverage,
        "is_pillar_complete": is_pillar_complete,
        "critical_competencies_covered": critical_covered,
        "scenario_count": len(accepted_dicts),
        "rejected_count": len(rejected_dicts),
    }


def _get_version_row(db: Session, package_id: str, version: int) -> KnowledgeGraphVersion:
    row = (
        db.query(KnowledgeGraphVersion)
        .filter_by(package_id=package_id, version_number=version)
        .first()
    )
    if row is None:
        raise NotFoundError(
            f"No graph version row found for package {package_id!r} at version {version}.",
            details={"package_id": package_id, "version": version},
        )
    return row


def compose_assessment_package_for_package(
    db: Session,
    package_id: str,
    version: Optional[int] = None,
    claude_client=None,
    judgment_mock: Optional[dict] = None,
    use_cache: bool = True,
) -> tuple[dict, bool]:
    """Load a package's graph (latest version, unless `version` is
    given), compose its assessment package, and cache the result keyed
    by (package_id, graph_version) so an identical graph version is
    never regenerated/revalidated twice. Returns (package_dict,
    cache_hit)."""
    payload = load_graph_version(db, package_id, version)

    def _builder() -> dict:
        return compose_assessment_package(
            payload, claude_client=claude_client, judgment_mock=judgment_mock
        )

    if use_cache:
        return get_or_build_scenario_package(package_id, payload.version, _builder)
    return _builder(), False


def persist_assessment_package(db: Session, package_dict: dict) -> AssessmentPackage:
    """Write a composed package_dict (from compose_assessment_package)
    into models.assessment.AssessmentPackage/Scenario rows. Status is
    "Validated" when the package is pillar-complete and carries at least
    one accepted scenario, "Rejected" when nothing was accepted, and
    "Draft" otherwise (accepted scenarios exist, but pillar coverage is
    incomplete -- still usable, but not yet a complete package)."""
    version_row = _get_version_row(db, package_dict["package_id"], package_dict["graph_version"])

    if package_dict["scenario_count"] == 0:
        status = "Rejected"
    elif package_dict["is_pillar_complete"]:
        status = "Validated"
    else:
        status = "Draft"

    package_row = AssessmentPackage(
        package_id=package_dict["package_id"],
        graph_version_id=version_row.id,
        status=status,
    )
    db.add(package_row)
    db.flush()

    for scenario in package_dict["scenarios"]:
        db.add(
            ScenarioRow(
                assessment_package_id=package_row.id,
                source_kind=scenario.get("source_kind"),
                source_id=scenario.get("source_id"),
                category=scenario["category"],
                difficulty=scenario["difficulty"],
                situation=scenario["situation"],
                context=scenario["context"],
                trigger=scenario["trigger"],
                decision_point=scenario["decision_point"],
                expected_evidence_json=json.dumps(scenario["expected_evidence"]),
                competency_mapping_json=json.dumps(scenario["competency_mapping"]),
                validation_status="Passed",
            )
        )

    db.flush()
    return package_row
