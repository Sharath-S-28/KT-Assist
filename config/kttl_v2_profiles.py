"""
config/kttl_v2_profiles.py — Pilot KTTL v2 Profile (Phase 4 / Wave 2-3,
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
access_path, Known Issue's resolution_path), state semantics, conflict
arbitration (Wave 2), and -- as of Wave 3 -- relationship requirements
(System depends-on), sufficiency rules (Known Issue, Task), one
evidence requirement (Known Issue), and dimension weights for KCS/KQS.
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
    relationship_requirements={
        "System": ["DEPENDS_ON"],  # matches config/ontology.py's System.required_relationships
    },
    sufficiency_rules={
        "Known Issue": "known_issue_min_viable_v1",
        "Task": "task_min_viable_v1",
    },
    evidence_requirements={
        "Known Issue": True,  # Critical/Important knowledge worth requiring a validation trail on
    },
    weights={
        # KCS family (must sum to 1 across TC/AC/RC -- renormalized if any is N/A)
        "wTC": 0.4, "wAC": 0.35, "wRC": 0.25,
        # KQS family (must sum to 1 across OS/EV -- renormalized if any is N/A)
        "wOS": 0.7, "wEV": 0.3,
    },
)

