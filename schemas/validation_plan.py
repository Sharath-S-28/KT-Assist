"""
schemas/validation_plan.py — ValidationPlan / EvaluatedRequirement
(Phase 4 / Wave 1, Hierarchical Knowledge Assurance redesign).

Ruling 4 (Phase 2 final rulings): coverage scoring and Finding detection
must consume the SAME evaluated requirement universe -- this is that
shared canonical representation. Built once per (graph_version,
profile) by services/coverage/validation_plan_builder.py (this same
wave); both the (future, later-wave) scoring engine and Finding
detectors read from one ValidationPlan instance, so applicability can
never be interpreted two different ways by two different modules.

Five applicable universes:
  U_TC — applicable required/optional object types
  U_AC — (object_id, attribute_name) pairs applicable under the profile
  U_RC — (object_id, relationship_type) pairs applicable under the profile
  U_OS — (object_id, sufficiency_rule_id) pairs applicable under the profile
  U_EV — (object_id, evidence_requirement) pairs applicable under the profile

For a v1-compatible profile (schemas/kttl_profile.py), U_AC/U_RC/U_OS/U_EV
are always empty sets by construction -- there are no attribute/
relationship/sufficiency/evidence requirements to evaluate -- which is
what makes AC/RC/OS/EV structurally N/A for v1 profiles.
"""

from dataclasses import dataclass, field


@dataclass
class EvaluatedRequirement:
    """One (object, requirement) pair plus its satisfaction and weight.
    `dimension` is one of TC/AC/RC/OS/EV."""

    object_id: str | None
    requirement_id: str
    dimension: str
    satisfied: bool
    weight: float


@dataclass
class ValidationPlan:
    graph_version_id: str
    profile_id: str
    profile_version: int

    U_TC: set[str] = field(default_factory=set)
    U_AC: set[tuple[str, str]] = field(default_factory=set)
    U_RC: set[tuple[str, str]] = field(default_factory=set)
    U_OS: set[tuple[str, str]] = field(default_factory=set)
    U_EV: set[tuple[str, str]] = field(default_factory=set)

    weights: dict[str, float] = field(default_factory=dict)
    # Traceability: which (object, requirement) pairs were considered
    # but excluded as a validly-approved NOT_APPLICABLE, rather than
    # never having been candidates at all (conditional-false case).
    excluded_as_na: dict[str, list[tuple[str, str]]] = field(default_factory=dict)
    # Wave 2: condition strings that failed to parse under the narrow
    # supported grammar -- a visible, inspectable defect list, never a
    # silent False. Each entry: (object_id, attribute_or_relation, condition).
    unsupported_conditions: list[tuple[str, str, str]] = field(default_factory=list)

    @property
    def is_v1_shaped(self) -> bool:
        """True when every rich-validation universe is empty -- the
        structural signal that this ValidationPlan was built from a
        v1-compatible profile and cannot produce AC/RC/OS/EV findings
        or trigger the Quality Gate."""
        return not (self.U_AC or self.U_RC or self.U_OS or self.U_EV)
