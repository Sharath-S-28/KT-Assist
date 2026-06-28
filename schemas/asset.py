"""
schemas/asset.py — Read contract for Knowledge Assets (Phase 11 / Session
33 addition).

Phase 11's Screen 3 (Knowledge Package Workspace) needs to list a
package's uploaded source documents -- the spec's literal proposal
("knowledge assets: documents, presentations, runbooks, recordings,
notes") is exactly models.asset.KnowledgeAsset, but, like the Knowledge
Graph Explorer's pre-existing gap (Phase 3/Session 9's graph_viewer had
no router), no router has ever exposed KnowledgeAsset over HTTP -- it
was only ever written to by the (not-yet-built) ingestion pipeline and
read directly by in-process services. Under the Phase 11 boundary rule
the frontend cannot reach the ORM directly, so this schema + the new
services/routers/assets.py close that gap the same way schemas/graph.py
+ services/routers/graph.py did for Screen 4.
"""

from schemas.common import TimestampedSchema


class AssetRead(TimestampedSchema):
    package_id: str
    filename: str
    file_type: str
    extraction_status: str
