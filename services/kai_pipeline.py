"""
services/kai_pipeline.py — Graph Assembly & Extraction Summary
(Phase 4 / KAI, Session 13).

Orchestrates the full KAI pipeline end to end:

  ingest_asset (S10) -> KAIAgent extraction (S11)
    -> KAIRelationshipAgent boundary-check + arbitration + relationship
       discovery (S12) -> save_graph_version as v1 (Session 8 storage)
    -> Knowledge Object Inventory / Confidence Report / Extraction
       Summary outputs.

This closes Phase 4: "Upload -> v1 graph -> inventory/summary"
completes with no manual intervention and is fully reproducible offline
under DEV_MODE mocks (no live Claude calls required to exercise the
whole chain).

KAI still does not calculate coverage, generate gaps/assessments, or
score readiness anywhere in this pipeline -- those are KVA/KGE/KRA/KASE
responsibilities in later phases.
"""

from dataclasses import dataclass, field
from typing import Any, Optional

from sqlalchemy.orm import Session

import config
from models import KnowledgeAsset, KnowledgeGraphVersion
from schemas.agent_contracts import AgentRequest
from schemas.graph import GraphPayload
from schemas.knowledge_graph import KnowledgeObject, Relationship
from services.asset_ingestion import ingest_asset
from services.claude_client import ClaudeClient
from services.graph_storage import save_graph_version
from services.kai_extraction import KAIAgent
from services.kai_relationship_discovery import KAIRelationshipAgent
from services.knowledge_model import validate_object, validate_relationship

LOW_CONFIDENCE_THRESHOLD = 0.5


def build_knowledge_object_inventory(objects: list[KnowledgeObject]) -> dict[str, Any]:
    """Typed object inventory: counts by type and by criticality, plus
    the full object list, for human review and downstream phases."""
    by_type: dict[str, int] = {}
    by_criticality: dict[str, int] = {}
    for obj in objects:
        by_type[obj.object_type] = by_type.get(obj.object_type, 0) + 1
        by_criticality[obj.criticality] = by_criticality.get(obj.criticality, 0) + 1

    return {
        "total_objects": len(objects),
        "by_type": by_type,
        "by_criticality": by_criticality,
        "objects": [obj.model_dump() for obj in objects],
    }


def build_confidence_report(objects: list[KnowledgeObject], relationships: list[Relationship]) -> dict[str, Any]:
    """Confidence is informational only (locked rule) -- this report
    surfaces it for a human reviewer; nothing downstream gates on it."""
    object_confidences = [obj.confidence for obj in objects]
    relationship_confidences = [rel.confidence for rel in relationships]

    return {
        "average_object_confidence": (
            sum(object_confidences) / len(object_confidences) if object_confidences else None
        ),
        "average_relationship_confidence": (
            sum(relationship_confidences) / len(relationship_confidences) if relationship_confidences else None
        ),
        "low_confidence_objects": [obj.id for obj in objects if obj.confidence < LOW_CONFIDENCE_THRESHOLD],
        "low_confidence_relationships": [
            rel.id for rel in relationships if rel.confidence < LOW_CONFIDENCE_THRESHOLD
        ],
        "note": "Confidence is informational only; it is never used to gate validation or scoring.",
    }


def build_extraction_summary(
    asset: KnowledgeAsset,
    chunk_count: int,
    pass1_object_count: int,
    relationship_result: dict[str, Any],
    version_row: KnowledgeGraphVersion,
    payload: GraphPayload,
) -> dict[str, Any]:
    return {
        "asset_id": asset.id,
        "filename": asset.filename,
        "content_hash": asset.content_hash,
        "chunks_processed": chunk_count,
        "objects_extracted_pass1": pass1_object_count,
        "objects_reconciled": len(payload.nodes),
        "boundary_batch_count": relationship_result["boundary_batch_count"],
        "relationships_discovered": len(relationship_result["relationships"]),
        "relationships_rejected": len(relationship_result["rejected_relationships"]),
        "graph_id": payload.graph_id,
        "graph_version": version_row.version_number,
    }


@dataclass
class KAIPipelineResult:
    asset: KnowledgeAsset
    graph_version: KnowledgeGraphVersion
    graph_payload: GraphPayload
    inventory: dict[str, Any] = field(default_factory=dict)
    confidence_report: dict[str, Any] = field(default_factory=dict)
    extraction_summary: dict[str, Any] = field(default_factory=dict)


def run_kai_pipeline(
    db: Session,
    package_id: str,
    filename: str,
    content: bytes,
    extraction_mock: Optional[dict[str, Any]] = None,
    boundary_mocks: Optional[list[dict[str, Any]]] = None,
    relationship_mock: Optional[dict[str, Any]] = None,
    claude_client: Optional[ClaudeClient] = None,
) -> KAIPipelineResult:
    """Run the full Upload -> v1 graph -> inventory/summary chain for
    one asset. Every Claude call inside (extraction, boundary checks,
    relationship discovery) shares one ClaudeClient instance so DEV_MODE
    + mock_response/boundary_mocks/relationship_mock make the whole run
    deterministic and reproducible offline with zero API spend."""
    client = claude_client or ClaudeClient()

    asset, chunks = ingest_asset(db, package_id, filename, content)

    extraction_agent = KAIAgent(claude_client=client)
    extraction_response = extraction_agent.run(
        AgentRequest(
            agent_name="KAI",
            package_id=package_id,
            payload={
                "asset_id": asset.id,
                "content_hash": asset.content_hash,
                "filename": asset.filename,
                "chunks": chunks,
                "mock_response": extraction_mock,
            },
        )
    )
    pass1_objects = extraction_response.result["objects"]

    if pass1_objects:
        relationship_agent = KAIRelationshipAgent(claude_client=client)
        relationship_response = relationship_agent.run(
            AgentRequest(
                agent_name="KAI",
                package_id=package_id,
                payload={
                    "objects": pass1_objects,
                    "content_hash": asset.content_hash,
                    "boundary_mock_responses": boundary_mocks,
                    "relationship_mock_response": relationship_mock,
                },
            )
        )
        relationship_result = relationship_response.result
    else:
        relationship_result = {
            "objects": [],
            "relationships": [],
            "rejected_relationships": [],
            "arbitration_log": [],
            "boundary_batch_count": 0,
        }

    nodes = [validate_object(raw) for raw in relationship_result["objects"]]
    relationships = [validate_relationship(raw) for raw in relationship_result["relationships"]]

    version_row, payload = save_graph_version(db, package_id, nodes, relationships)

    inventory = build_knowledge_object_inventory(nodes)
    confidence_report = build_confidence_report(nodes, relationships)
    summary = build_extraction_summary(
        asset, len(chunks), len(pass1_objects), relationship_result, version_row, payload
    )

    return KAIPipelineResult(
        asset=asset,
        graph_version=version_row,
        graph_payload=payload,
        inventory=inventory,
        confidence_report=confidence_report,
        extraction_summary=summary,
    )
