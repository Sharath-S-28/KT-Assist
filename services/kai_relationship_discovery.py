"""
services/kai_relationship_discovery.py — Relationship Discovery &
Confidence (Phase 4 / KAI, Session 12).

Implements the second half of KAI's hybrid two-pass extraction model:

  Pass 1 (Session 11): per-chunk object extraction -> candidate objects.
  Pass 2 (this module): batched semantic boundary checks (10 objects
    per Claude call, config.SEMANTIC_BATCH_SIZE) re-examine the pooled
    candidate set for duplicates/merges/rejects across chunks.

Python arbitration (arbitrate_objects) reconciles pass 1 + pass 2 into
a single object set — Claude proposes, Python decides; this is the
"hybrid two-pass model with Python arbitration" locked design decision.

Relationship discovery then runs once over the reconciled object set,
proposing typed edges with per-relationship confidence (informational
only, same rule as object confidence). Every proposed relationship is
re-validated in Python against schemas.knowledge_graph.RELATIONSHIP_TYPE_RULES
and referential integrity before being accepted — Claude's draft never
gets to silently corrupt the graph.
"""

import uuid
from typing import Any, Optional

import config
from schemas.agent_contracts import AgentRequest
from schemas.knowledge_graph import RELATIONSHIP_TYPE_RULES, KnowledgeObject, Relationship
from services.base_agent import BaseAgent
from services.claude_client import ClaudeClient
from services.knowledge_model import validate_graph, validate_object, validate_relationship
from utils.errors import ValidationFailedError

# ---------------------------------------------------------------------------
# Pass 2: batched semantic boundary checks
# ---------------------------------------------------------------------------

BOUNDARY_CHECK_SYSTEM_PROMPT = """\
You are reviewing a pooled inventory of knowledge objects extracted
from multiple document chunks of the same source. Objects extracted
from different chunks may actually describe the same real-world thing
(duplicates to merge), may be too coarse or too fine, or may not
belong in the inventory at all.

For each object in this batch, return a verdict:
  - "confirm": the object is correct as-is.
  - "merge": this object duplicates another object in the inventory;
    set merge_with to that other object's id.
  - "split": the object actually bundles more than one distinct thing
    (flag only; do not attempt the split yourself).
  - "reject": the object should not exist (e.g. hallucinated, or an
    individual UI step that violates the granularity rule).

Respond with JSON only:
{
  "verdicts": [
    {"object_id": "string", "verdict": "confirm | merge | split | reject",
     "merge_with": "string or null", "note": "string or null"}
  ]
}
"""


def build_boundary_check_payload(batch: list[KnowledgeObject]) -> dict[str, Any]:
    return {
        "objects": [
            {
                "id": obj.id,
                "object_type": obj.object_type,
                "name": obj.name,
                "description": obj.description,
            }
            for obj in batch
        ]
    }


def _batch_objects(objects: list[KnowledgeObject], batch_size: int) -> list[list[KnowledgeObject]]:
    return [objects[i : i + batch_size] for i in range(0, len(objects), batch_size)]


def run_boundary_checks(
    client: ClaudeClient,
    objects: list[KnowledgeObject],
    content_hash: str,
    mock_responses: Optional[list[dict[str, Any]]] = None,
) -> tuple[list[dict[str, Any]], int]:
    """Run the batched (10-per-call) semantic boundary check pass.
    Returns (all verdicts pooled across batches, number of batches used)."""
    batches = _batch_objects(objects, config.SEMANTIC_BATCH_SIZE)
    all_verdicts: list[dict[str, Any]] = []

    for batch_index, batch in enumerate(batches):
        cache_key = f"{content_hash}:boundary:{batch_index}"
        mock = mock_responses[batch_index] if mock_responses and batch_index < len(mock_responses) else None

        response = client.complete(
            system_prompt=BOUNDARY_CHECK_SYSTEM_PROMPT,
            user_payload=build_boundary_check_payload(batch),
            cache_dir=config.KAI_CACHE_DIR,
            cache_key=cache_key,
            mock_response=mock,
        )
        all_verdicts.extend(response.get("verdicts", []))

    return all_verdicts, len(batches)


def arbitrate_objects(
    objects: list[KnowledgeObject],
    verdicts: list[dict[str, Any]],
) -> tuple[list[KnowledgeObject], list[dict[str, Any]]]:
    """Python arbitration: reconcile pass-1 objects against pass-2
    verdicts into a single deduplicated object set. An object with no
    verdict (boundary check didn't cover it, e.g. mock gaps) defaults
    to 'confirm' — silence is not grounds for rejection."""
    verdict_by_object_id = {v["object_id"]: v for v in verdicts if "object_id" in v}
    objects_by_id = {obj.id: obj for obj in objects}
    dropped_ids: set[str] = set()
    log: list[dict[str, Any]] = []

    for obj in objects:
        verdict = verdict_by_object_id.get(obj.id, {"verdict": "confirm"})
        action = verdict.get("verdict", "confirm")

        if action == "reject":
            dropped_ids.add(obj.id)
            log.append({"object_id": obj.id, "action": "rejected", "note": verdict.get("note")})

        elif action == "merge":
            target_id = verdict.get("merge_with")
            target = objects_by_id.get(target_id) if target_id else None
            if target is not None and target.id != obj.id:
                dropped_ids.add(obj.id)
                if obj.description and obj.description not in target.description:
                    target.description = (target.description + " " + obj.description).strip()
                log.append({"object_id": obj.id, "action": "merged_into", "target_id": target.id})
            else:
                log.append({
                    "object_id": obj.id,
                    "action": "confirmed",
                    "note": "merge target missing/invalid; kept as-is",
                })

        elif action == "split":
            log.append({"object_id": obj.id, "action": "flagged_for_split", "note": verdict.get("note")})

        else:
            log.append({"object_id": obj.id, "action": "confirmed"})

    reconciled = [obj for obj in objects if obj.id not in dropped_ids]
    return reconciled, log


# ---------------------------------------------------------------------------
# Relationship discovery
# ---------------------------------------------------------------------------

RELATIONSHIP_DISCOVERY_SYSTEM_PROMPT = """\
You are discovering typed relationships between an already-finalized
set of knowledge objects. Only use these relationship types, each
restricted to the given source-object-type -> target-object-type pair:
{type_pairs}

Assign a confidence score (0.0-1.0) per relationship reflecting how
clearly the source text supports it. Confidence is informational only
and will never be used to gate validation.

Respond with JSON only:
{{
  "relationships": [
    {{"id": "string", "relationship_type": "one of the types above",
      "source_id": "string", "target_id": "string", "confidence": 0.0}}
  ]
}}
""".format(
    type_pairs="\n".join(
        f"  - {rel_type}: {pair[0]} -> {pair[1]}" for rel_type, pair in RELATIONSHIP_TYPE_RULES.items()
    )
)


def build_relationship_payload(objects: list[KnowledgeObject]) -> dict[str, Any]:
    return {
        "objects": [
            {"id": obj.id, "object_type": obj.object_type, "name": obj.name}
            for obj in objects
        ]
    }


def discover_relationships(
    client: ClaudeClient,
    objects: list[KnowledgeObject],
    content_hash: str,
    mock_response: Optional[dict[str, Any]] = None,
) -> tuple[list[Relationship], list[dict[str, Any]]]:
    """Single Claude call proposing relationships over the (already
    reconciled) object set. Every proposal is re-validated in Python
    against type-pair rules and referential integrity; only accepted
    relationships are returned, rejects are reported separately for
    transparency rather than silently dropped."""
    objects_by_id = {obj.id: obj for obj in objects}
    cache_key = f"{content_hash}:relationships"

    response = client.complete(
        system_prompt=RELATIONSHIP_DISCOVERY_SYSTEM_PROMPT,
        user_payload=build_relationship_payload(objects),
        cache_dir=config.KAI_CACHE_DIR,
        cache_key=cache_key,
        mock_response=mock_response,
    )

    accepted: list[Relationship] = []
    rejected: list[dict[str, Any]] = []

    for raw_rel in response.get("relationships", []):
        raw_rel = dict(raw_rel)
        raw_rel.setdefault("id", str(uuid.uuid4()))

        try:
            rel = validate_relationship(raw_rel)
        except ValidationFailedError as exc:
            rejected.append({"raw": raw_rel, "reason": str(exc)})
            continue

        source = objects_by_id.get(rel.source_id)
        target = objects_by_id.get(rel.target_id)
        if source is None or target is None:
            rejected.append({"raw": raw_rel, "reason": "source/target object not found in reconciled set"})
            continue

        expected_pair = RELATIONSHIP_TYPE_RULES.get(rel.relationship_type)
        if expected_pair and (source.object_type, target.object_type) != expected_pair:
            rejected.append({
                "raw": raw_rel,
                "reason": (
                    f"type-pair mismatch: {rel.relationship_type} requires "
                    f"{expected_pair}, got ({source.object_type}, {target.object_type})"
                ),
            })
            continue

        accepted.append(rel)

    return accepted, rejected


# ---------------------------------------------------------------------------
# Agent entry point
# ---------------------------------------------------------------------------

class KAIRelationshipAgent(BaseAgent):
    """Runs pass 2 (batched boundary checks) + Python arbitration over a
    pooled object set from Session 11, then discovers relationships
    over the reconciled result. Same KAI agent boundary as
    services.kai_extraction.KAIAgent — KAI never calculates coverage,
    gaps, assessments, or readiness."""

    agent_name = "KAI"
    forbidden_actions = (
        "calculate_coverage",
        "generate_gaps",
        "generate_assessments",
        "score_readiness",
    )

    def __init__(self, claude_client: Optional[ClaudeClient] = None):
        super().__init__()
        self.client = claude_client or ClaudeClient()

    def validate_input(self, request: AgentRequest) -> None:
        payload = request.payload
        for key in ("objects", "content_hash"):
            if key not in payload:
                raise ValidationFailedError(f"KAI relationship-discovery payload missing required key {key!r}.")
        if not isinstance(payload["objects"], list) or not payload["objects"]:
            raise ValidationFailedError("KAI relationship-discovery payload 'objects' must be a non-empty list.")

    def execute(self, request: AgentRequest) -> dict[str, Any]:
        payload = request.payload
        content_hash = payload["content_hash"]
        objects = [validate_object(raw) for raw in payload["objects"]]
        boundary_mocks = payload.get("boundary_mock_responses")
        relationship_mock = payload.get("relationship_mock_response")

        verdicts, batch_count = run_boundary_checks(self.client, objects, content_hash, boundary_mocks)
        reconciled_objects, arbitration_log = arbitrate_objects(objects, verdicts)

        accepted_rels, rejected_rels = discover_relationships(
            self.client, reconciled_objects, content_hash, relationship_mock
        )

        return {
            "objects": [obj.model_dump() for obj in reconciled_objects],
            "relationships": [rel.model_dump() for rel in accepted_rels],
            "rejected_relationships": rejected_rels,
            "arbitration_log": arbitration_log,
            "boundary_batch_count": batch_count,
        }

    def validate_output(self, result: dict[str, Any]) -> None:
        objects = [validate_object(raw) for raw in result["objects"]]
        relationships = [validate_relationship(raw) for raw in result["relationships"]]

        graph_result = validate_graph(objects, relationships)
        if not graph_result.valid:
            raise ValidationFailedError(
                "Reconciled object/relationship set failed graph validation.",
                details={"errors": graph_result.errors},
            )
