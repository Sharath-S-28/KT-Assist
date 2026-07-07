"""
scripts/seed_demo_hierarchical_kai_cache.py — demo-mode branch only.

Step 1 finding: the pilot profile (config.kttl_v2_profiles.PILOT_PROFILE)
makes services.agents.kai_extraction._chunk_cache_key append a
":pilot-v{N}" suffix whenever pilot_object_types is non-empty -- so the
existing data/cache/kai/{hash}:{chunk}.json files scripts/seed_demo_kai_cache.py
already wrote are NOT hit by ingest_hierarchical(); a cache miss there
would fall through to DEV_MODE's generic mock, which carries no
"attributes" key at all for System/Known Issue/Task. This script writes
the missing pilot-keyed cache entries.

Does NOT duplicate the underlying object/relationship graph: imports
OBJECTS_BY_CHUNK/RELATIONSHIPS/CONTENT_HASH directly from
scripts/seed_demo_kai_cache.py and only overlays
services.demo.hierarchical_kai_attributes.PILOT_ATTRIBUTE_OVERLAY onto
matching System/Known Issue/Task objects.

NOTE (issue_log.md #13): this script previously also injected additive
System -> Dependency DEPENDS_ON edges into the shared relationships
cache. That has been REMOVED -- discover_relationships() only consults
RELATIONSHIP_TYPE_RULES (primary), never RELATIONSHIP_TYPE_RULES_ADDITIONAL,
so those edges were silently dropped during ingestion regardless of
being seeded (62 seeded -> 56 persisted -> RC=0.0, confirmed
empirically). The relationships cache written here is now just the
legacy 56-edge set, unmodified. Each System's DEPENDS_ON gap is instead
opened for real (RELATIONSHIP_GAP, rule_family "failure_recovery") and
closed through the hierarchical closure loop -- see
services/demo/hierarchical_gap_answers.py's _RELATIONSHIP_ANSWERS.
"""

import copy
import json
from pathlib import Path

from scripts.seed_demo_kai_cache import CONTENT_HASH, OBJECTS_BY_CHUNK, RELATIONSHIPS
from services.agents.kai_extraction import _chunk_cache_key
from services.demo.hierarchical_kai_attributes import PILOT_ATTRIBUTE_OVERLAY

KAI_CACHE_DIR = Path("data/cache/kai")
PILOT_OBJECT_TYPES = {"System", "Known Issue", "Task"}


def _sanitized_cache_path(cache_dir: Path, cache_key: str) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    safe_key = cache_key.replace(":", "-")
    return cache_dir / f"{safe_key}.json"


def _overlay_attributes(objects: list[dict]) -> list[dict]:
    overlaid = []
    for obj in objects:
        obj = copy.deepcopy(obj)
        if obj["object_type"] in PILOT_OBJECT_TYPES and obj["id"] in PILOT_ATTRIBUTE_OVERLAY:
            obj["attributes"] = PILOT_ATTRIBUTE_OVERLAY[obj["id"]]
        overlaid.append(obj)
    return overlaid


def main() -> None:
    total_objects = 0
    total_with_attributes = 0

    for chunk_index, objects in enumerate(OBJECTS_BY_CHUNK):
        overlaid = _overlay_attributes(objects)
        cache_key = _chunk_cache_key(CONTENT_HASH, chunk_index, PILOT_OBJECT_TYPES)
        path = _sanitized_cache_path(KAI_CACHE_DIR, cache_key)
        path.write_text(json.dumps({"objects": overlaid}, indent=2))
        total_objects += len(overlaid)
        total_with_attributes += sum(1 for o in overlaid if "attributes" in o)
        print(f"chunk {chunk_index}: {len(overlaid)} objects "
              f"({sum(1 for o in overlaid if 'attributes' in o)} with pilot attributes) -> {path}")

    # Write the shared relationships cache -- same key both legacy and
    # hierarchical ingestion read. No System->Dependency edges injected
    # here anymore (issue_log.md #13); those gaps close via the
    # hierarchical closure loop instead.
    rel_cache_key = f"{CONTENT_HASH}:relationships"
    rel_path = _sanitized_cache_path(KAI_CACHE_DIR, rel_cache_key)
    rel_path.write_text(json.dumps({"relationships": list(RELATIONSHIPS)}, indent=2))
    print(f"relationships: {len(RELATIONSHIPS)} (legacy set, unmodified) -> {rel_path}")

    print(f"content_hash: {CONTENT_HASH}")
    print(f"total pilot-cache objects: {total_objects} ({total_with_attributes} carrying pilot attributes)")


if __name__ == "__main__":
    main()
