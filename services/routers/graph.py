"""
services/routers/graph.py — FastAPI router for the Knowledge Graph
Explorer (Phase 3 / Session 9 capability, exposed over HTTP for Phase 11
/ Session 33's Screen 4).

Why this router exists now and not in Phase 3: Session 9 built
services/graph_viewer.py (PyVis HTML render + node detail panel) as a
pure service, with no router, because nothing outside the backend
needed it yet. The Phase 11 spec assumes Screen 4 can "reuse the
existing S9 PyVis HTML output" -- but the frontend boundary guard
(Phase 11's locked architectural rule, see frontend/api_client.py)
forbids any Streamlit page from importing services.graph_viewer or
services.graph_storage directly. So Screen 4 needs this router whether
the spec wrote it down or not; it is reconciled here the same way
Session 32 reconciled its own missing pieces against the real codebase.

Endpoints:
  GET /api/packages/{package_id}/graph                -> GraphPayload (JSON; latest version, or ?version=N)
  GET /api/packages/{package_id}/graph/html           -> text/html (raw PyVis-rendered page)
  GET /api/packages/{package_id}/graph/nodes/{node_id} -> NodeDetail
  GET /api/packages/{package_id}/graph/versions        -> version/change-history list
"""

import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from database import get_db
from schemas.graph import GraphPayload, NodeDetail
from services.graph_storage import list_graph_versions, load_graph_version
from services.graph_viewer import get_node_detail, render_graph_html

router = APIRouter(prefix="/api/packages", tags=["graph"])


@router.get("/{package_id}/graph", response_model=GraphPayload)
def get_graph(package_id: str, version: Optional[int] = None, db: Session = Depends(get_db)):
    return load_graph_version(db, package_id, version=version)


@router.get("/{package_id}/graph/html", response_class=HTMLResponse)
def get_graph_html(package_id: str, version: Optional[int] = None, db: Session = Depends(get_db)):
    payload = load_graph_version(db, package_id, version=version)
    out_dir = Path(tempfile.mkdtemp(prefix="kt_graph_html_"))
    out_path = out_dir / f"{package_id}.html"
    render_graph_html(payload, out_path)
    return HTMLResponse(content=out_path.read_text())


@router.get("/{package_id}/graph/nodes/{node_id}", response_model=NodeDetail)
def get_graph_node(package_id: str, node_id: str, version: Optional[int] = None, db: Session = Depends(get_db)):
    payload = load_graph_version(db, package_id, version=version)
    detail = get_node_detail(payload, node_id)
    return NodeDetail(
        id=detail.id,
        object_type=detail.object_type,
        name=detail.name,
        description=detail.description,
        criticality=detail.criticality,
        confidence=detail.confidence,
        source_reference=detail.source_reference,
        outgoing_relationships=detail.outgoing_relationships,
        incoming_relationships=detail.incoming_relationships,
    )


@router.get("/{package_id}/graph/versions")
def get_graph_versions(package_id: str, db: Session = Depends(get_db)):
    rows = list_graph_versions(db, package_id)
    return [
        {
            "version_number": row.version_number,
            "node_count": row.node_count,
            "relationship_count": row.relationship_count,
            "change_summary": row.change_summary,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]
