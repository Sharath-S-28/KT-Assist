"""
config/kttl_v2_profiles.py — Pilot KTTL v2 Profile (Phase 4 / Wave 2,
Hierarchical Knowledge Assurance redesign).

Prototype storage decision (ruling): v2 profiles live in configuration
code alongside existing domain configuration (config/domain.py's
KNOWLEDGE_TYPE_TEMPLATES). No database-managed profile storage for the
prototype. Profile loading stays version-aware (schemas/kttl_profile.py
distinguishes v1-compat-loaded profiles from explicitly-authored v2
ones) so v1 compatibility is unaffected by this file's existence.

One small, real profile -- System + Known Issue + Task -- deliberately
NOT a full enterprise ontology. Exercises: mandatory attributes
(all three types), one conditional attribute (Known Issue's
escalation_condition), deterministic N/A handling (System's
access_path, Known Issue's resolution_path), state semantics, and
(via services/agents/attribute_arbitration.py) conflict arbitration.
"""

from schemas.kttl_profile import KTTLProfileV2

PILOT_PROFILE = KTTLProfileV2(
    profile_id="pilot-hierarchical-assurance-v2",
    version=2,
    required_types=["System", "Known Issue", "Task"],
    optional_types=[],
    attribute_requirements={
        "System": ["system_name", "purpose", "access_path"],
        "Known Issue": ["trigger", "impact", "detection_method", "resolution_path"],
        "Task": ["trigger_condition", "execution_steps", "responsible_role", "validation_criteria"],
    },
    relationship_requirements={},  # not exercised by this pilot -- attribute-level focus only
    sufficiency_rules={},  # Wave 2 scope excludes Finding detectors/sufficiency rules
    evidence_requirements={},  # Wave 2 scope excludes evidence/validation gap detection
)
