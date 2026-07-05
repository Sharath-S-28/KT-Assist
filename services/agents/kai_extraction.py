"""
services/kai_extraction.py — KAI Object Extraction & Classification
(Phase 4 / KAI, Session 11).

Implements the KAI prompt architecture (system prompt = framework
context + task instructions + output contract; data payload = the
per-chunk extraction request) and the KAIAgent itself, which turns one
knowledge asset's text chunks into a typed object inventory.

Extraction is cached by content_hash (services/asset_ingestion.py's
hash) so an unchanged asset never re-hits the Claude API — caching is
delegated to services.claude_client.ClaudeClient, which already
implements the cache-dir/cache-key contract; this module just supplies
config.KAI_CACHE_DIR and a per-chunk cache key.

KAI must NOT calculate coverage, generate gaps/assessments, or score
readiness (Appendix D) — enforced via BaseAgent.forbidden_actions.
"""

import uuid
from typing import Any, Optional

import config
from config.ontology import get_object_type_spec
from schemas.agent_contracts import AgentRequest
from schemas.knowledge_element_state import AttributeEvidence, AttributeValue, KnowledgeElementState
from schemas.knowledge_graph import KnowledgeObject
from services.agents.attribute_arbitration import CLAUDE_PROPOSABLE_STATES
from services.core.base_agent import BaseAgent
from services.core.claude_client import ClaudeClient
from services.graph.knowledge_model import validate_object
from utils.errors import ValidationFailedError

# ---------------------------------------------------------------------------
# Prompt architecture
# ---------------------------------------------------------------------------

FRAMEWORK_CONTEXT = """\
You are extracting knowledge objects for a Knowledge Transition program.
Every object you produce MUST be one of these nine types:
{object_types}

Every object MUST be assigned exactly one criticality level:
{criticalities}

Granularity rule: extract Processes and Tasks only down to the Task
level. Never create a separate object for an individual UI step or
click-by-click instruction - fold that detail into the Task's
description instead.
""".format(
    object_types="\n".join(f"  - {t}" for t in config.KNOWLEDGE_OBJECT_TYPES),
    criticalities="\n".join(f"  - {c}" for c in config.CRITICALITY_WEIGHTS),
)

TASK_INSTRUCTIONS = """\
Task: read the provided document chunk and extract every distinct
knowledge object it describes. For each object, assign a stable id,
its object_type, a short name, a one-or-two-sentence description, a
criticality level (your best judgment of operational importance), a
confidence score between 0.0 and 1.0 reflecting how clearly the source
text supports this object (confidence is informational only - it is
never used to gate validation), and a source_reference noting where in
the chunk this came from (e.g. a short quote or section label).
"""

OUTPUT_CONTRACT = """\
Respond with JSON only, matching exactly this shape:
{
  "objects": [
    {
      "id": "string, unique within this response",
      "object_type": "one of the nine types above",
      "name": "string",
      "description": "string",
      "criticality": "Critical | Important | Supporting",
      "confidence": 0.0,
      "source_reference": "string or null"
    }
  ]
}
No other top-level keys are permitted.
"""


def build_system_prompt() -> str:
    """System prompt = framework context + task instructions + output
    contract, composed in that fixed order. Unchanged from Wave 1/
    pre-redesign -- legacy callers get byte-identical behavior."""
    return "\n\n".join([FRAMEWORK_CONTEXT, TASK_INSTRUCTIONS, OUTPUT_CONTRACT])


def _pilot_attribute_schema_text(pilot_object_types: set[str]) -> str:
    lines = []
    for object_type in sorted(pilot_object_types):
        spec = get_object_type_spec(object_type)
        attrs = list(spec.mandatory_attributes) + [c.attribute for c in spec.conditional_attributes]
        lines.append(f"  {object_type}: {', '.join(attrs)}")
    return "\n".join(lines)


PILOT_TASK_INSTRUCTIONS = """\
Wave 2 pilot: for objects of these specific types only, ALSO extract \
structured attributes:
{pilot_schema}

For each attribute you can address, propose ONE of exactly these three \
states -- never any other value:
  - PRESENT: you found a specific value, grounded in the text.
  - EXPLICITLY_UNKNOWN: the text explicitly says this isn't known \
(e.g. "I don't know who owns this").
  - NOT_APPLICABLE: the text explicitly indicates this doesn't apply \
here. Propose this only when the source text supports it -- you are \
proposing, not deciding; a separate deterministic process confirms or \
rejects it.

Do not propose an attribute you have no textual grounds for at all --\
 simply omit it. Never guess a value to fill a field.

For every proposed attribute, include source_reference (a short quote \
or section label) and, if you can identify one, source_excerpt_id. \
Do not invent an excerpt id if you cannot identify one -- omit it \
rather than fabricate.
"""

PILOT_OUTPUT_CONTRACT_ADDENDUM = """\
For objects of the pilot types listed above, ALSO include an \
"attributes" key on that object:
{
  "attributes": {
    "attribute_name": {
      "value": "string or null",
      "proposed_state": "PRESENT | EXPLICITLY_UNKNOWN | NOT_APPLICABLE",
      "source_reference": "string or null",
      "source_excerpt_id": "string or null"
    }
  }
}
Objects of any other type must NOT include an "attributes" key.
"""


def build_pilot_system_prompt(pilot_object_types: set[str]) -> str:
    """Extended system prompt used ONLY when the caller explicitly opts
    into pilot-mode extraction for a given set of object types. Legacy
    build_system_prompt() is completely untouched by this function's
    existence."""
    pilot_instructions = PILOT_TASK_INSTRUCTIONS.format(pilot_schema=_pilot_attribute_schema_text(pilot_object_types))
    return "\n\n".join([FRAMEWORK_CONTEXT, TASK_INSTRUCTIONS, pilot_instructions, OUTPUT_CONTRACT, PILOT_OUTPUT_CONTRACT_ADDENDUM])


def build_data_payload(chunk_text: str, asset_id: str, chunk_index: int, filename: str) -> dict[str, Any]:
    """The data payload half of the architecture: just the chunk plus
    enough metadata for the source_reference to be meaningful."""
    return {
        "asset_id": asset_id,
        "filename": filename,
        "chunk_index": chunk_index,
        "chunk_text": chunk_text,
    }


# Bumped whenever the pilot extraction contract's shape changes, so a
# schema change causes a clean cache miss rather than misinterpreting
# an old cache entry under the new shape. Legacy (non-pilot) calls never
# include this segment, so their cache keys and existing cache entries
# are completely unaffected.
PILOT_EXTRACTION_SCHEMA_VERSION = 1


def _chunk_cache_key(content_hash: str, chunk_index: int, pilot_object_types: Optional[set[str]] = None) -> str:
    if not pilot_object_types:
        return f"{content_hash}:{chunk_index}"
    return f"{content_hash}:{chunk_index}:pilot-v{PILOT_EXTRACTION_SCHEMA_VERSION}"


def _parse_pilot_attributes(raw_attributes: dict[str, Any], extraction_run_id: str) -> dict[str, AttributeValue]:
    """Parse Claude's raw per-chunk attribute proposals defensively.
    Only PRESENT/EXPLICITLY_UNKNOWN/NOT_APPLICABLE are ever trusted from
    Claude (CLAUDE_PROPOSABLE_STATES) -- anything else (a malformed or
    hallucinated state name, e.g. "NOT_OBSERVED" or "CONFLICTING", which
    are Python-only assignments) is dropped to NOT_OBSERVED rather than
    trusted. This is single-chunk-grounded only; cross-chunk arbitration
    (services/agents/attribute_arbitration.py) is a separate step this
    function does not perform.
    """
    parsed: dict[str, AttributeValue] = {}
    for attr_name, raw in raw_attributes.items():
        if not isinstance(raw, dict):
            continue
        try:
            state = KnowledgeElementState(raw.get("proposed_state"))
        except ValueError:
            state = KnowledgeElementState.NOT_OBSERVED
        if state not in CLAUDE_PROPOSABLE_STATES:
            state = KnowledgeElementState.NOT_OBSERVED
        evidence = AttributeEvidence(
            source_reference=raw.get("source_reference"),
            source_excerpt_id=raw.get("source_excerpt_id"),
            extraction_run_id=extraction_run_id,
        )
        parsed[attr_name] = AttributeValue(
            value=raw.get("value") if state == KnowledgeElementState.PRESENT else None,
            state=state,
            evidence=evidence,
        )
    return parsed


class KAIAgent(BaseAgent):
    """Extracts and classifies knowledge objects from a knowledge
    asset's text chunks. One Claude call per chunk (cached by
    content_hash:chunk_index); results are concatenated into a single
    typed object inventory for the asset."""

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
        for key in ("asset_id", "content_hash", "chunks", "filename"):
            if key not in payload:
                raise ValidationFailedError(f"KAI extraction payload missing required key {key!r}.")
        if not isinstance(payload["chunks"], list):
            raise ValidationFailedError("KAI extraction payload 'chunks' must be a list of strings.")

    def execute(self, request: AgentRequest) -> dict[str, Any]:
        payload = request.payload
        asset_id = payload["asset_id"]
        content_hash = payload["content_hash"]
        filename = payload["filename"]
        chunks: list[str] = payload["chunks"]
        mock_response = payload.get("mock_response")
        # Wave 2: opt-in only. None/empty => every code path below behaves
        # exactly as it did before this wave existed.
        pilot_object_types: set[str] = set(payload.get("pilot_object_types") or ())
        extraction_run_id = payload.get("extraction_run_id", asset_id)

        all_objects: list[KnowledgeObject] = []
        any_cache_miss = False

        system_prompt = (
            build_pilot_system_prompt(pilot_object_types) if pilot_object_types else build_system_prompt()
        )

        for chunk_index, chunk_text in enumerate(chunks):
            cache_key = _chunk_cache_key(content_hash, chunk_index, pilot_object_types)
            cache_hit_before = self.client.cache_enabled and self.client._read_cache(
                config.KAI_CACHE_DIR, cache_key
            ) is not None

            response = self.client.complete(
                system_prompt=system_prompt,
                user_payload=build_data_payload(chunk_text, asset_id, chunk_index, filename),
                cache_dir=config.KAI_CACHE_DIR,
                cache_key=cache_key,
                mock_response=mock_response,
            )

            if not cache_hit_before:
                any_cache_miss = True

            for raw_obj in response.get("objects", []):
                raw_obj = dict(raw_obj)
                raw_obj.setdefault("id", str(uuid.uuid4()))
                raw_obj.setdefault("source_reference", None)
                raw_attributes = raw_obj.pop("attributes", None)
                obj = validate_object(raw_obj)
                if raw_attributes and obj.object_type in pilot_object_types:
                    obj.attributes = _parse_pilot_attributes(raw_attributes, extraction_run_id)
                all_objects.append(obj)

        return {
            "asset_id": asset_id,
            "objects": [obj.model_dump() for obj in all_objects],
            "cached": not any_cache_miss,
        }

    def validate_output(self, result: dict[str, Any]) -> None:
        if "objects" not in result:
            raise ValidationFailedError("KAI extraction result missing 'objects'.")
        for raw_obj in result["objects"]:
            validate_object(raw_obj)
