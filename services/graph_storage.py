"""
services/graph_storage.py — Versioned knowledge graph JSON persistence
(Phase 3 / Session 8).

v1 is the initial KAI extraction; v2..vn are KGE enrichment increments.
Each version is written as its own immutable JSON file under
config.GRAPH_STORAGE_DIR/{package_id}/v{n}.json; the indexed pointer +
summary lives in the KnowledgeGraphVersion row (models/asset.py). This
module never overwrites a prior version's file — change history is the
sequence of files itself.
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
from services.knowledge_model import validate_graph
from utils.errors import NotFoundError, ValidationFailedError


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
            graph_id = json.loads(Path(previous.storage_path).read_text())["graph_id"]
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
        storage_path=str(storage_path),
        node_count=payload.node_count,
        relationship_count=payload.relationship_count,
        change_summary=change_summary,
    )
    db.add(version_row)
    db.flush()

    return version_row, payload


def load_graph_version(db: Session, package_id: str, version: Optional[int] = None) -> GraphPayload:
    """Load a specific version's payload (or the latest, if version is
    None) by round-tripping its JSON file back into a GraphPayload."""
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

    raw = json.loads(Path(row.storage_path).read_text())
    return GraphPayload(**raw)


def list_graph_versions(db: Session, package_id: str) -> list[KnowledgeGraphVersion]:
    """Full version/change history for a package, oldest first."""
    return (
        db.query(KnowledgeGraphVersion)
        .filter_by(package_id=package_id)
        .order_by(KnowledgeGraphVersion.version_number.asc())
        .all()
    )
