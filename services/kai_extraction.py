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
from schemas.agent_contracts import AgentRequest
from schemas.knowledge_graph import KnowledgeObject
from services.base_agent import BaseAgent
from services.claude_client import ClaudeClient
from services.knowledge_model import validate_object
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
    contract, composed in that fixed order."""
    return "\n\n".join([FRAMEWORK_CONTEXT, TASK_INSTRUCTIONS, OUTPUT_CONTRACT])


def build_data_payload(chunk_text: str, asset_id: str, chunk_index: int, filename: str) -> dict[str, Any]:
    """The data payload half of the architecture: just the chunk plus
    enough metadata for the source_reference to be meaningful."""
    return {
        "asset_id": asset_id,
        "filename": filename,
        "chunk_index": chunk_index,
        "chunk_text": chunk_text,
    }


def _chunk_cache_key(content_hash: str, chunk_index: int) -> str:
    return f"{content_hash}:{chunk_index}"


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

        all_objects: list[KnowledgeObject] = []
        any_cache_miss = False

        for chunk_index, chunk_text in enumerate(chunks):
            cache_key = _chunk_cache_key(content_hash, chunk_index)
            cache_hit_before = self.client.cache_enabled and self.client._read_cache(
                config.KAI_CACHE_DIR, cache_key
            ) is not None

            response = self.client.complete(
                system_prompt=build_system_prompt(),
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
                all_objects.append(validate_object(raw_obj))

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
