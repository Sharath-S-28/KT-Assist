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
scripts/seed_demo_kai_cache.py and only (a) overlays
services.demo.hierarchical_kai_attributes.PILOT_ATTRIBUTE_OVERLAY onto
matching System/Known Issue/Task objects, and (b) appends
SYSTEM_DEPENDS_ON_EDGES to the SAME data/cache/kai/{hash}:relationships.json
file the legacy path also reads (relationship discovery's cache key
does not fork on pilot mode -- see services/agents/kai_relationship_discovery.py's
discover_relationships) -- additive only, never removing an existing edge,
so the already-seeded legacy v1 DB checkpoint is unaffected.
"""

import copy
import json
from pathlib import Path

from scripts.seed_demo_kai_cache import CONTENT_HASH, OBJECTS_BY_CHUNK, RELATIONSHIPS
from services.agents.kai_extraction import _chunk_cache_key
from services.demo.hierarchical_kai_attributes import PILOT_ATTRIBUTE_OVERLAY, SYSTEM_DEPENDS_ON_EDGES

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

    # Extend (never replace) the shared relationships cache -- same key
    # both legacy and hierarchical ingestion read.
    rel_cache_key = f"{CONTENT_HASH}:relationships"
    rel_path = _sanitized_cache_path(KAI_CACHE_DIR, rel_cache_key)
    existing = json.loads(rel_path.read_text())["relationships"] if rel_path.exists() else list(RELATIONSHIPS)
    existing_ids = {r["id"] for r in existing}
    added = [r for r in SYSTEM_DEPENDS_ON_EDGES if r["id"] not in existing_ids]
    combined = existing + added
    rel_path.write_text(json.dumps({"relationships": combined}, indent=2))
    print(f"relationships: {len(existing)} existing + {len(added)} added System->Dependency = {len(combined)} -> {rel_path}")

    print(f"content_hash: {CONTENT_HASH}")
    print(f"total pilot-cache objects: {total_objects} ({total_with_attributes} carrying pilot attributes)")


if __name__ == "__main__":
    main()
