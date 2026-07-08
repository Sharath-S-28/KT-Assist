"""
services/graph_storage.py — Versioned knowledge graph JSON persistence
(Phase 3 / Session 8; path-portability fix issue_log #21).

v1 is the initial KAI extraction; v2..vn are KGE enrichment increments.
Each version is written as its own immutable JSON file under
config.GRAPH_STORAGE_DIR/{package_id}/v{n}.json; the indexed pointer +
summary lives in the KnowledgeGraphVersion row (models/asset.py). This
module never overwrites a prior version's file — change history is the
sequence of files itself.

KnowledgeGraphVersion.storage_path is persisted as a PORTABLE,
repository-relative path (e.g. "data/graphs/{package_id}/v{n}.json"),
resolved at read time against config.BASE_DIR -- never as a machine-
specific absolute path. Both save_graph_version() and
load_graph_version() resolve storage_path through the single
_resolve_graph_path() policy below; no other module may duplicate this
logic (see services/explanation/explanation_data_layer.py,
services/routers/graph.py, services/routers/demo_hierarchical.py,
services/orchestration/workflow_runner.py -- all consume graph payloads
through this module and inherit the fix automatically).
"""

import json
import uuid
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

import config
from models import KnowledgeGraphVersion
from schemas.graph import GraphPayload
from schemas.knowledge_graph import KnowledgeObject, Relationship
from services.graph.knowledge_model import validate_graph
from utils.errors import NotFoundError, ValidationFailedError


class GraphArtifactNotFoundError(NotFoundError):
    """Raised when a KnowledgeGraphVersion row's storage_path cannot be
    resolved to an existing graph JSON file, even after portable-path
    and legacy-absolute-path relocation attempts. Never silently
    substituted with a different version or an empty/fabricated
    payload -- the caller must repair the path (see
    scripts/migrate_graph_storage_paths.py) or reseed."""

    error_code = "graph_artifact_not_found"


def _portable_storage_path(package_id: str, version_number: int) -> str:
    """The canonical, repository-relative form written to
    KnowledgeGraphVersion.storage_path going forward -- portable across
    machines and operating systems."""
    return str(Path("data") / "graphs" / package_id / f"v{version_number}.json")


def _resolve_graph_path(storage_path: str, package_id: str, version_number: int) -> Path:
    """Centralized path-resolution policy (issue_log #21). Tries, in
    order:
      1. storage_path as a portable, repo-relative path, resolved
         against config.BASE_DIR (the canonical form).
      2. storage_path as-is, if it happens to be a valid absolute path
         in THIS environment (e.g. unchanged machine/OS since it was
         written).
      3. Deterministic relocation: every graph file's canonical name is
         always v{version_number}.json under
         config.GRAPH_STORAGE_DIR/{package_id}/, regardless of what
         machine/OS wrote the stored path -- so re-deriving that exact
         location from (package_id, version_number) recovers legacy
         absolute paths (Linux, Windows, prior temp directories) without
         needing to parse or repair the stored string.
    Raises GraphArtifactNotFoundError (never FileNotFoundError, never a
    silent fallback to another version or an empty payload) if none of
    these resolve to an existing file."""
    tried: list[str] = []
    candidate = Path(storage_path)

    if not candidate.is_absolute():
        portable = (config.BASE_DIR / candidate).resolve()
        tried.append(str(portable))
        if portable.is_file():
            return portable

    tried.append(str(candidate))
    if candidate.is_absolute() and candidate.is_file():
        return candidate

    expected = config.GRAPH_STORAGE_DIR / package_id / f"v{version_number}.json"
    tried.append(str(expected))
    if expected.is_file():
        return expected

    raise GraphArtifactNotFoundError(
        f"Graph artifact for package {package_id!r} version {version_number} could not be located "
        f"in this environment (tried: {tried}). The stored path is likely from a different "
        "machine or OS. Run `python -m scripts.migrate_graph_storage_paths` to repair portable "
        "storage paths where the underlying file still exists locally, or reseed the demo if it "
        "genuinely does not.",
        details={"package_id": package_id, "version_number": version_number, "tried_paths": tried},
    )


def _package_dir(package_id: str) -> Path:
    path = config.GRAPH_STORAGE_DIR / package_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _latest_version_row(db: Session, package_id: str) -> Optional[KnowledgeGraphVersion]:
    return (
        db.query(KnowledgeGraphVersion)
        .filter_by(package_id=package_id)
        .order_by(KnowledgeGraphVersion.version_number.desc())
        .first()
    )


def save_graph_version(
    db: Session,
    package_id: str,
    nodes: list[KnowledgeObject],
    relationships: list[Relationship],
    change_summary: Optional[str] = None,
    graph_id: Optional[str] = None,
) -> tuple[KnowledgeGraphVersion, GraphPayload]:
    """Validate, serialize and persist the next version of a package's
    knowledge graph. Raises ValidationFailedError if the object/
    relationship set doesn't pass services.knowledge_model.validate_graph.
    """
    result = validate_graph(nodes, relationships)
    if not result.valid:
        raise ValidationFailedError(
            "Knowledge graph failed validation; refusing to persist.",
            details={"errors": result.errors},
        )

    previous = _latest_version_row(db, package_id)
    next_version = (previous.version_number + 1) if previous else 1

    if next_version == 1 and change_summary:
        raise ValidationFailedError(
            "change_summary must be empty for v1 (the initial extraction); "
            "only enrichment increments (v2..vn) carry a change summary."
        )

    if graph_id is None:
        if previous is not None:
            previous_path = _resolve_graph_path(previous.storage_path, package_id, previous.version_number)
            graph_id = json.loads(previous_path.read_text())["graph_id"]
        else:
            graph_id = str(uuid.uuid4())

    payload = GraphPayload(
        graph_id=graph_id,
        package_id=package_id,
        version=next_version,
        nodes=nodes,
        relationships=relationships,
        change_summary=change_summary,
    )

    storage_path = _package_dir(package_id) / f"v{next_version}.json"
    storage_path.write_text(payload.model_dump_json(indent=2))

    version_row = KnowledgeGraphVersion(
        package_id=package_id,
        version_number=next_version,
        storage_path=_portable_storage_path(package_id, next_version),
        node_count=payload.node_count,
        relationship_count=payload.relationship_count,
        change_summary=change_summary,
    )
    db.add(version_row)
    db.flush()

    return version_row, payload


def load_graph_version(db: Session, package_id: str, version: Optional[int] = None) -> GraphPayload:
    """Load a specific version's payload (or the latest, if version is
    None) by round-tripping its JSON file back into a GraphPayload.
    Resolves storage_path through the centralized, portable path policy
    (_resolve_graph_path) -- never falls back to a different version
    number than the one requested/latest-as-of-this-row."""
    query = db.query(KnowledgeGraphVersion).filter_by(package_id=package_id)
    if version is not None:
        row = query.filter_by(version_number=version).first()
    else:
        row = query.order_by(KnowledgeGraphVersion.version_number.desc()).first()

    if row is None:
        raise NotFoundError(
            f"No graph version found for package {package_id!r}"
            + (f" at version {version}" if version is not None else ""),
            details={"package_id": package_id, "version": version},
        )

    resolved_path = _resolve_graph_path(row.storage_path, package_id, row.version_number)
    raw = json.loads(resolved_path.read_text())
    return GraphPayload(**raw)


def list_graph_versions(db: Session, package_id: str) -> list[KnowledgeGraphVersion]:
    """Full version/change history for a package, oldest first."""
    return (
        db.query(KnowledgeGraphVersion)
        .filter_by(package_id=package_id)
        .order_by(KnowledgeGraphVersion.version_number.asc())
        .all()
    )
