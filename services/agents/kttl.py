"""
services/kttl.py — Knowledge Type Template Library & Template
Intelligence Engine (Phase 5 / KVA, Session 14).

KTTL (config.KNOWLEDGE_TYPE_TEMPLATES) defines, per package type, which
knowledge object types are expected (required) vs nice-to-have
(optional) for that kind of package. The Template Intelligence Engine
in this module consumes a v1+ graph's object-type composition and
either matches it to the single best-fitting template or blends the
top two templates when the package looks hybrid — locked design
decision: "Template selection: Template Intelligence Engine with
auto-detection and blending."

Scoring combines two signals so neither dominates:
  - required_recall: how much of the template's *required* set is
    actually present (a template can't win just by having a big,
    loosely-related optional set).
  - jaccard: how well the *whole* expected set (required + optional)
    explains the present object types, penalizing templates whose
    expected set barely overlaps the graph.

KVA boundary: this module only determines/describes the expected-object
profile for a package. It does not calculate coverage, generate gaps,
or score readiness — those are Sessions 15-17.
"""

from dataclasses import dataclass, field

import config
from schemas.graph import GraphPayload

REQUIRED_RECALL_WEIGHT = 0.5
JACCARD_WEIGHT = 0.5

# If the top two template scores differ by less than this, the package is
# treated as hybrid and the two templates are blended rather than picking
# a single winner.
BLEND_SCORE_GAP = 0.08

# A template's score must clear this floor to be eligible for blending at
# all — otherwise a sparse/empty graph would "blend" with everything just
# because every template scores equally low.
BLEND_MIN_SCORE = 0.5


@dataclass
class TemplateMatch:
    package_type: str
    required_types: list[str] = field(default_factory=list)
    optional_types: list[str] = field(default_factory=list)
    # The one or two source template names this match was built from.
    blended_from: list[str] = field(default_factory=list)
    # Every template's raw score, for transparency/debugging.
    scores: dict[str, float] = field(default_factory=dict)

    @property
    def is_blended(self) -> bool:
        return len(self.blended_from) > 1


def _present_object_types(payload: GraphPayload) -> set[str]:
    return {node.object_type for node in payload.nodes}


def _score_template(template_name: str, present_types: set[str]) -> float:
    template = config.KNOWLEDGE_TYPE_TEMPLATES[template_name]
    required = set(template["required"])
    optional = set(template["optional"])
    expected = required | optional

    required_recall = len(present_types & required) / len(required) if required else 0.0

    union = present_types | expected
    jaccard = len(present_types & expected) / len(union) if union else 0.0

    return REQUIRED_RECALL_WEIGHT * required_recall + JACCARD_WEIGHT * jaccard


def score_all_templates(payload: GraphPayload) -> dict[str, float]:
    """Score every known template against this graph's object-type
    composition. Higher is a better fit; scores are in [0.0, 1.0]."""
    present_types = _present_object_types(payload)
    return {
        name: round(_score_template(name, present_types), 4)
        for name in config.KNOWLEDGE_TYPE_TEMPLATES
    }


def _merge_templates(names: list[str]) -> tuple[list[str], list[str]]:
    """Union required across blended templates; union optional, minus
    anything already required (a type can't be both required and
    optional in the merged profile)."""
    required: set[str] = set()
    optional: set[str] = set()
    for name in names:
        template = config.KNOWLEDGE_TYPE_TEMPLATES[name]
        required |= set(template["required"])
        optional |= set(template["optional"])
    optional -= required
    return sorted(required), sorted(optional)


def detect_package_template(payload: GraphPayload) -> TemplateMatch:
    """Auto-detect (or blend) the expected-object template for a package
    from its current graph composition. Never requires manual template
    selection — this is the only entry point callers need."""
    scores = score_all_templates(payload)
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)

    best_name, best_score = ranked[0]
    second_name, second_score = ranked[1] if len(ranked) > 1 else (None, 0.0)

    if (
        second_name is not None
        and (best_score - second_score) < BLEND_SCORE_GAP
        and second_score >= BLEND_MIN_SCORE
    ):
        blended_names = [best_name, second_name]
        required, optional = _merge_templates(blended_names)
        return TemplateMatch(
            package_type=" + ".join(blended_names) + " (Blended)",
            required_types=required,
            optional_types=optional,
            blended_from=blended_names,
            scores=scores,
        )

    template = config.KNOWLEDGE_TYPE_TEMPLATES[best_name]
    return TemplateMatch(
        package_type=best_name,
        required_types=list(template["required"]),
        optional_types=list(template["optional"]),
        blended_from=[best_name],
        scores=scores,
    )
