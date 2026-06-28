"""
services/traceability_service.py — Explanation Engine traceability tree
(Phase 9 / Session 29).

Materializes the canonical, longest-form [FROZEN] chain from Chunk 9:

    Readiness -> OIS -> Pillar -> Competency -> Evidence -> Scenario
    -> Knowledge Object

every other chain quoted in the build spec (Chunk 6's "OIS -> Pillar ->
Competency -> Evidence Marker -> Assessment Response", Chunk 8 Screen 9's
"Scenario -> Evidence -> Competency -> Pillar -> OIS") is the same chain
read in a different direction or truncated -- this module builds the one
tree and callers/drill-down walk whichever sub-path they need.

Reads ExplanationData (Layer 1's output -- no new numbers originate
here) plus the database, purely for human-readable labels (scenario
situation text, knowledge-object names) that ExplanationData doesn't
carry. Label lookups are best-effort: a missing row/payload degrades to
using the bare id as the label rather than raising, since a label is
display sugar, not a fact.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel
from sqlalchemy.orm import Session

from models import KnowledgeGraphVersion, Scenario as ScenarioRow
from schemas.explanation import ExplanationData
from services.graph_storage import load_graph_version

TraceLevel = str  # "readiness" | "ois" | "pillar" | "competency" | "evidence" | "scenario" | "knowledge_object"


class TraceNode(BaseModel):
    level: TraceLevel
    id: str
    label: str
    value: Optional[float] = None
    children: list["TraceNode"] = []


TraceNode.model_rebuild()


class TraceabilityService:
    def __init__(self, session: Session):
        self.db = session
        self._node_name_cache: dict[str, dict[str, str]] = {}  # graph_version_id -> {node_id: name}

    def build_tree(self, data: ExplanationData) -> TraceNode:
        pillar_nodes = [self._build_pillar_node(pillar) for pillar in data.pillars]

        ois_node = TraceNode(
            level="ois",
            id=f"{data.receiver_readiness_id}-ois",
            label=f"OIS {data.ois:g}",
            value=data.ois,
            children=pillar_nodes,
        )

        return TraceNode(
            level="readiness",
            id=data.receiver_readiness_id,
            label=f"Readiness: {data.readiness_decision}",
            value=None,
            children=[ois_node],
        )

    def drill(self, data: ExplanationData, level: str, node_id: str) -> Optional[TraceNode]:
        """Return the subtree rooted at (level, node_id), or None if not
        found -- Screen 9's lazy-expansion endpoint."""
        return self._find(self.build_tree(data), level, node_id)

    def _find(self, node: TraceNode, level: str, node_id: str) -> Optional[TraceNode]:
        if node.level == level and node.id == node_id:
            return node
        for child in node.children:
            found = self._find(child, level, node_id)
            if found is not None:
                return found
        return None

    # -- per-level builders ------------------------------------------------

    def _build_pillar_node(self, pillar) -> TraceNode:
        return TraceNode(
            level="pillar",
            id=pillar.pillar_id,
            label=pillar.name,
            value=pillar.score,
            children=[self._build_competency_node(c) for c in pillar.competencies],
        )

    def _build_competency_node(self, competency) -> TraceNode:
        return TraceNode(
            level="competency",
            id=competency.competency_id,
            label=competency.name,
            value=competency.score,
            children=[self._build_evidence_node(e) for e in competency.evidence],
        )

    def _build_evidence_node(self, evidence) -> TraceNode:
        return TraceNode(
            level="evidence",
            id=evidence.marker_id,
            label=f"{evidence.marker_id}: {evidence.state}",
            value=evidence.score,
            children=[self._build_scenario_node(evidence.scenario_id, evidence.knowledge_object_ids)],
        )

    def _build_scenario_node(self, scenario_id: str, knowledge_object_ids: list[str]) -> TraceNode:
        label = self._scenario_label(scenario_id)
        children = [
            TraceNode(
                level="knowledge_object",
                id=ko_id,
                label=self._knowledge_object_label(scenario_id, ko_id),
                value=None,
                children=[],
            )
            for ko_id in knowledge_object_ids
        ]
        return TraceNode(level="scenario", id=scenario_id, label=label, value=None, children=children)

    # -- label lookups (best-effort, never raise) ---------------------------

    def _scenario_label(self, scenario_id: str) -> str:
        scenario = self.db.query(ScenarioRow).filter_by(id=scenario_id).first()
        if scenario is None:
            return scenario_id
        situation = scenario.situation or ""
        return situation[:80] if situation else scenario_id

    def _knowledge_object_label(self, scenario_id: str, ko_id: str) -> str:
        scenario = self.db.query(ScenarioRow).filter_by(id=scenario_id).first()
        if scenario is None:
            return ko_id

        version_row = (
            self.db.query(KnowledgeGraphVersion)
            .filter_by(id=scenario.assessment_package.graph_version_id)
            .first()
        )
        if version_row is None:
            return ko_id

        names = self._node_name_cache.get(version_row.id)
        if names is None:
            try:
                payload = load_graph_version(self.db, version_row.package_id, version_row.version_number)
                names = {node.id: node.name for node in payload.nodes}
            except Exception:
                names = {}
            self._node_name_cache[version_row.id] = names

        return names.get(ko_id, ko_id)
