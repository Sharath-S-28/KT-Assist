"""
tests/test_session14_kttl.py — Phase 5 / Session 14 success criterion:
a package is matched (or blended) to the correct expected-object
profile without manual template selection.
"""

import config
from schemas.graph import GraphPayload
from schemas.knowledge_graph import KnowledgeObject
from services.kttl import (
    BLEND_MIN_SCORE,
    BLEND_SCORE_GAP,
    detect_package_template,
    score_all_templates,
)


def _obj(id_, object_type, name="x"):
    return KnowledgeObject(
        id=id_, object_type=object_type, name=name, description="", criticality="Important",
    )


def _payload(object_types: list[str]) -> GraphPayload:
    nodes = [_obj(f"o{i}", t, f"{t} {i}") for i, t in enumerate(object_types)]
    return GraphPayload(graph_id="g1", package_id="pkg-1", version=1, nodes=nodes, relationships=[])


# ---------------------------------------------------------------------------
# KTTL data integrity
# ---------------------------------------------------------------------------

def test_every_template_uses_valid_object_types_with_no_required_optional_overlap():
    for name, template in config.KNOWLEDGE_TYPE_TEMPLATES.items():
        required = set(template["required"])
        optional = set(template["optional"])
        assert required.issubset(set(config.KNOWLEDGE_OBJECT_TYPES))
        assert optional.issubset(set(config.KNOWLEDGE_OBJECT_TYPES))
        assert required.isdisjoint(optional), f"{name} has overlapping required/optional types"
        assert required, f"{name} must have at least one required type"


# ---------------------------------------------------------------------------
# Pure (non-hybrid) matches — auto-detected, no manual template argument
# ---------------------------------------------------------------------------

def test_pure_dashboard_graph_matches_dashboard_without_blending():
    payload = _payload(config.KNOWLEDGE_TYPE_TEMPLATES["Dashboard"]["required"])
    match = detect_package_template(payload)

    assert match.package_type == "Dashboard"
    assert not match.is_blended
    assert match.blended_from == ["Dashboard"]
    assert set(match.required_types) == set(config.KNOWLEDGE_TYPE_TEMPLATES["Dashboard"]["required"])


def test_pure_python_application_graph_matches_python_application_without_blending():
    payload = _payload(config.KNOWLEDGE_TYPE_TEMPLATES["Python Application"]["required"])
    match = detect_package_template(payload)

    assert match.package_type == "Python Application"
    assert not match.is_blended


def test_pure_operations_graph_matches_operations_without_blending():
    payload = _payload(config.KNOWLEDGE_TYPE_TEMPLATES["Operations"]["required"])
    match = detect_package_template(payload)

    assert match.package_type == "Operations"
    assert not match.is_blended


# ---------------------------------------------------------------------------
# Hybrid packages — auto-blended
# ---------------------------------------------------------------------------

def test_hybrid_graph_blends_python_application_and_operations():
    # Process/Task shared; System+Dependency are Python App-only,
    # Escalation+Known Issue are Operations-only -- an even mix of both.
    payload = _payload(["Process", "Task", "System", "Dependency", "Escalation", "Known Issue"])
    match = detect_package_template(payload)

    assert match.is_blended
    assert set(match.blended_from) == {"Python Application", "Operations"}
    assert "Blended" in match.package_type
    # Merged required profile should equal exactly what's present.
    assert set(match.required_types) == {"Process", "Task", "System", "Dependency", "Escalation", "Known Issue"}
    # No type may appear in both required and optional after merging.
    assert set(match.required_types).isdisjoint(set(match.optional_types))


def test_blend_thresholds_are_the_documented_values():
    # Locks the success criterion's "auto-detection and blending" knobs
    # so a future change to these constants is a deliberate, visible diff.
    assert BLEND_SCORE_GAP == 0.08
    assert BLEND_MIN_SCORE == 0.5


# ---------------------------------------------------------------------------
# Scoring transparency & edge cases
# ---------------------------------------------------------------------------

def test_score_all_templates_returns_bounded_score_per_template():
    payload = _payload(["Process", "Task", "System", "Business Rule"])
    scores = score_all_templates(payload)

    assert set(scores.keys()) == set(config.KNOWLEDGE_TYPE_TEMPLATES.keys())
    for score in scores.values():
        assert 0.0 <= score <= 1.0


def test_empty_graph_does_not_crash_and_does_not_blend():
    payload = _payload([])
    match = detect_package_template(payload)

    assert all(score == 0.0 for score in match.scores.values())
    assert not match.is_blended
    assert match.package_type in config.KNOWLEDGE_TYPE_TEMPLATES


def test_detection_requires_no_manual_template_argument():
    # The only input is the graph payload itself -- confirms "without
    # manual template selection" at the API level, not just behaviorally.
    import inspect
    from services.kttl import detect_package_template as fn

    params = list(inspect.signature(fn).parameters)
    assert params == ["payload"]
