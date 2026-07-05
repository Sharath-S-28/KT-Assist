"""
schemas/kttl_profile.py — KTTL v2 Profile Schema + v1 Compatibility
Loader (Phase 4 / Wave 1, Hierarchical Knowledge Assurance redesign).

v1 profiles (today's config.KNOWLEDGE_TYPE_TEMPLATES -- a flat
{"required": [...], "optional": [...]} per package_type) are wrapped,
never migrated, into this richer shape: `load_v1_compatible()` produces
a KTTLProfileV2 whose attribute/relationship/sufficiency/evidence
requirement dicts are all EMPTY. This emptiness is what later
guarantees (via services/coverage/validation_plan_builder.py, this same
wave) that U_AC/U_RC/U_OS/U_EV are structurally empty for any
unmigrated profile -- which is what makes "v1 profiles never trigger
Quality Gate" a structural property of the universe construction rather
than a runtime check someone could accidentally bypass.

Existing config/domain.py templates are NOT modified.
"""

from dataclasses import dataclass, field

import config


@dataclass
class KTTLProfileV2:
    profile_id: str
    version: int
    required_types: list[str] = field(default_factory=list)
    optional_types: list[str] = field(default_factory=list)
    # Empty by default for every field below -- a v1-compat profile
    # leaves all of these empty, which is the whole point.
    attribute_requirements: dict[str, list[str]] = field(default_factory=dict)
    relationship_requirements: dict[str, list[str]] = field(default_factory=dict)
    sufficiency_rules: dict[str, str] = field(default_factory=dict)
    evidence_requirements: dict[str, bool] = field(default_factory=dict)
    weights: dict[str, float] = field(default_factory=dict)

    @property
    def is_v1_compatible(self) -> bool:
        """True when this profile carries no rich-validation
        requirements at all -- i.e. behaves exactly like today's engine."""
        return not (
            self.attribute_requirements
            or self.relationship_requirements
            or self.sufficiency_rules
            or self.evidence_requirements
        )


def load_v1_compatible(package_type: str) -> KTTLProfileV2:
    """Wrap an existing config.KNOWLEDGE_TYPE_TEMPLATES entry as a
    KTTLProfileV2 with empty rich-validation requirement sets.
    Raises KeyError for an unregistered package_type, matching today's
    existing lookup behavior rather than silently defaulting."""
    if package_type not in config.KNOWLEDGE_TYPE_TEMPLATES:
        raise KeyError(f"No KTTL template registered for package_type={package_type!r}")
    template = config.KNOWLEDGE_TYPE_TEMPLATES[package_type]
    return KTTLProfileV2(
        profile_id=package_type,
        version=1,
        required_types=list(template["required"]),
        optional_types=list(template.get("optional", [])),
    )
