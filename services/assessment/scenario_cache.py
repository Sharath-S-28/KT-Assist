"""
services/scenario_cache.py — Scenario Package Caching by Graph Version
(Phase 7 / KRA, Session 23).

Cost-control locked decision: an assessment package (the generated +
weighted + validated scenario set) is expensive to (re)produce, so once
one graph version has been turned into a package, identical graph
versions must reuse the cached result rather than regenerating and
re-validating from scratch. Cache key is (package_id, version_number) --
a graph version's contents are immutable once written
(services/graph_storage.py never overwrites a version file), so the pair
is a stable, sufficient cache key with no separate content hash needed.

Storage is a flat JSON file per (package_id, version) under
config.SCENARIO_CACHE_DIR, mirroring the on-disk versioning pattern
already established for graphs themselves (config.GRAPH_STORAGE_DIR).

KRA boundary (non-negotiable): this module only stores/retrieves
previously computed scenario packages. It must NOT calculate OIS,
determine readiness, or modify the graph.
"""

import json
from pathlib import Path
from typing import Callable, Optional

import config


def _cache_path(package_id: str, version: int) -> Path:
    package_dir = config.SCENARIO_CACHE_DIR / package_id
    package_dir.mkdir(parents=True, exist_ok=True)
    return package_dir / f"v{version}.json"


def cache_key(package_id: str, version: int) -> str:
    return f"{package_id}:v{version}"


def save_scenario_package_cache(package_id: str, version: int, package_data: dict) -> Path:
    """Persist a serializable scenario package for this exact graph
    version. Overwrites any prior cache entry for the same key (a graph
    version's own contents never change, but a package may legitimately
    be regenerated under a new SGF rule set, in which case the cache is
    expected to be invalidated/overwritten deliberately by the caller)."""
    path = _cache_path(package_id, version)
    path.write_text(json.dumps(package_data, indent=2))
    return path


def load_scenario_package_cache(package_id: str, version: int) -> Optional[dict]:
    """Return the cached package for this (package_id, version), or
    None if no cache entry exists or caching is globally disabled
    (config.CACHE_ENABLED)."""
    if not config.CACHE_ENABLED:
        return None
    path = _cache_path(package_id, version)
    if not path.exists():
        return None
    return json.loads(path.read_text())


def invalidate_scenario_package_cache(package_id: str, version: int) -> bool:
    """Remove a cache entry, if present. Returns True if a file was
    actually removed."""
    path = _cache_path(package_id, version)
    if path.exists():
        path.unlink()
        return True
    return False


def get_or_build_scenario_package(
    package_id: str,
    version: int,
    builder_fn: Callable[[], dict],
) -> tuple[dict, bool]:
    """Cache-through accessor: return (package_data, cache_hit). On a
    cache miss (or when caching is disabled), builder_fn() is invoked
    exactly once and its result is persisted for next time."""
    cached = load_scenario_package_cache(package_id, version)
    if cached is not None:
        return cached, True

    built = builder_fn()
    if config.CACHE_ENABLED:
        save_scenario_package_cache(package_id, version, built)
    return built, False
