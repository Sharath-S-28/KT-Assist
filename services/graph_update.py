"""
services/graph_update.py — Graph Update, Versioning & Recalculation Loop
(Phase 6 / KGE, Session 19).

Applies one Session 18 InterpretationResult (a gap response's structured
object/relationship change proposals) to a package's current graph:
  - new objects are appended, updated objects are merged onto the
    existing node by id (relationship maintenance: every prior
    relationship is carried forward untouched; only new edges are
    added);
  - the result is persisted as the next graph version (v(n+1)) via
    services/graph_storage.save_graph_version, with an auto-generated
    change_summary -- the change log;
  - coverage is recalculated on the new graph through services/kva.py's
    run_kva, so the post-update sufficiency decision is computed by the
    exact same Python logic Session 17 already locked in -- this module
    never re-implements or diverges from that threshold/criteria check;
  - the coverage delta (new - previous) is reported alongside the new
    KVAResult.

KGE boundary (non-negotiable): this module updates the graph and
recalculates coverage only. It must NOT generate assessments, calculate
readiness, or modify competency scores -- those belong to KRA/KASE.
"""

import uuid
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from models.coverage import CoverageResult
from schemas.graph import GraphPayload
from schemas.knowledge_graph import KnowledgeObject, Relationship
from services.coverage_persistence import persist_coverage_result
from services.graph_storage import load_graph_version, save_graph_version
from services.kttl import detect_package_template
from services.coverage_engine import compute_coverage
from services.kva import KVAResult, run_kva
from services.response_interpretation import InterpretationResult
from utils.errors import ValidationFailedError


def apply_interpreted_changes(
    payload: GraphPayload, interpretation: InterpretationResult
) -> tuple[list[KnowledgeObject], list[Relationship], str]:
    """Merge one InterpretationResult onto an existing graph payload.

    Returns (nodes, relationships, change_summary) ready for
    save_graph_version. Every existing node/relationship is carried
    forward unchanged unless explicitly targeted by an "update" object
    change; new objects/relationships are appended."""
    nodes_by_id: dict[str, KnowledgeObject] = {node.id: node for node in payload.nodes}
    node_order: list[str] = [node.id for node in payload.nodes]
    name_to_id: dict[str, str] = {node.name: node.id for node in payload.nodes}

    created_types: list[str] = []
    updated_count = 0

    for change in interpretation.object_changes:
        if change.action == "create":
            new_id = str(uuid.uuid4())
            new_node = KnowledgeObject(
                id=new_id,
                object_type=change.object_type,
                name=change.name,
                description=change.description,
                criticality=change.criticality,
                confidence=1.0,  # provider/SME-confirmed -- highest confidence by convention
                source_reference="gap_response",
            )
            nodes_by_id[new_id] = new_node
            node_order.append(new_id)
            name_to_id[new_node.name] = new_id
            created_types.append(change.object_type)
        elif change.action == "update":
            if not change.target_object_id or change.target_object_id not in nodes_by_id:
                raise ValidationFailedError(
                    f"Cannot update object: target_object_id {change.target_object_id!r} not found in graph.",
                    details={"target_object_id": change.target_object_id},
                )
            existing = nodes_by_id[change.target_object_id]
            updated = existing.model_copy(
                update={
                    "description": change.description,
                    "criticality": change.criticality,
                }
            )
            nodes_by_id[change.target_object_id] = updated
            updated_count += 1
        else:
            raise ValidationFailedError(f"Unrecognized object change action: {change.action!r}")

    relationships = list(payload.relationships)
    new_relationship_count = 0

    for rel_change in interpretation.relationship_changes:
        if rel_change.source_name not in name_to_id:
            raise ValidationFailedError(
                f"Cannot create relationship: no object named {rel_change.source_name!r} in graph.",
                details={"source_name": rel_change.source_name},
            )
        if rel_change.target_name not in name_to_id:
            raise ValidationFailedError(
                f"Cannot create relationship: no object named {rel_change.target_name!r} in graph.",
                details={"target_name": rel_change.target_name},
            )
        relationships.append(
            Relationship(
                id=str(uuid.uuid4()),
                relationship_type=rel_change.relationship_type,
                source_id=name_to_id[rel_change.source_name],
                target_id=name_to_id[rel_change.target_name],
                confidence=1.0,
            )
        )
        new_relationship_count += 1

    nodes = [nodes_by_id[node_id] for node_id in node_order]

    summary_parts = []
    if created_types:
        summary_parts.append(f"added {len(created_types)} object(s) ({', '.join(created_types)})")
    if updated_count:
        summary_parts.append(f"updated {updated_count} object(s)")
    if new_relationship_count:
        summary_parts.append(f"added {new_relationship_count} relationship(s)")
    change_summary = "Gap closure: " + (", ".join(summary_parts) if summary_parts else "no changes") + "."

    return nodes, relationships, change_summary


@dataclass
class GraphUpdateResult:
    package_id: str
    previous_version: int
    new_version: int
    previous_coverage_score: float
    new_coverage_score: float
    coverage_delta: float
    change_summary: str
    kva_result: KVAResult
    coverage_result: "CoverageResult"  # the row this update just persisted

    @property
    def loop_terminated(self) -> bool:
        """Loop termination rule (Session 19 spec, identical to Session
        17's gate): Coverage >= threshold AND no Critical gaps AND no
        High-risk open gaps. Delegates entirely to KVAResult.is_sufficient
        -- never re-implemented here."""
        return self.kva_result.is_sufficient


def close_gap(
    db: Session,
    package_id: str,
    interpretation: InterpretationResult,
    claude_client=None,
) -> GraphUpdateResult:
    """Apply one gap response's interpreted changes to the package's
    current graph, version it, and recalculate coverage end to end."""
    previous_payload = load_graph_version(db, package_id)
    previous_template = detect_package_template(previous_payload)
    previous_coverage_score = compute_coverage(previous_payload, previous_template).coverage_score

    nodes, relationships, change_summary = apply_interpreted_changes(previous_payload, interpretation)

    version_row, new_payload = save_graph_version(
        db, package_id, nodes, relationships, change_summary=change_summary
    )

    kva_result = run_kva(new_payload, claude_client=claude_client)
    coverage_delta = kva_result.coverage_score - previous_coverage_score

    # [Bug fix, round 2]: this is the actual live (non-demo) caller of
    # run_kva() in the entire codebase -- services/routers/gaps.py's
    # submit_gap_response calls close_gap directly on every real gap
    # response a user submits. Previously this function returned
    # kva_result inline for the HTTP response but never persisted it,
    # so any later read (e.g. the Validation Center dashboard) saw
    # stale or missing CoverageResult data even though a correct
    # computation had genuinely just happened. version_row.id is this
    # iteration's own fresh graph version -- not a stale id carried
    # over from ingestion -- so a multi-gap closure loop correctly gets
    # one CoverageResult row per version, matching the FK's own implied
    # cardinality (see services/coverage_persistence.py for the full
    # history, including the versioning bug found and fixed alongside
    # this one).
    coverage_result = persist_coverage_result(
        db, package_id, version_row.id, kva_result
    )

    return GraphUpdateResult(
        package_id=package_id,
        previous_version=previous_payload.version,
        new_version=version_row.version_number,
        previous_coverage_score=previous_coverage_score,
        new_coverage_score=kva_result.coverage_score,
        coverage_delta=coverage_delta,
        change_summary=change_summary,
        kva_result=kva_result,
        coverage_result=coverage_result,
    )
