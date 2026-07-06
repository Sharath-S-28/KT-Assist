"""
services/demo/hierarchical_fixtures.py — demo-mode only.

Ruling A (fixed deterministic demo identities): pinned UUIDs for the
hierarchical demo's program, package, and 3 receivers. Kept inside this
demo fixture layer only -- never imported into config/ or any
production code path. models.mixins.UUIDPrimaryKeyMixin's id column
accepts any explicit string id at construction (its uuid4 default only
applies when no id is passed), so these are ordinary, valid primary
keys, just fixed instead of random.

Why pinned: services/assessment/scenario_cache.py's cache key is
literally (package_id, version) -- a fresh random package_id on every
demo reset would invalidate that cache (and, if a live model were ever
configured, force a real re-generation call). Pinning makes the whole
replay chain -- KAI cache, scenario cache, this fixture layer's own
gap-answer/receiver-strategy lookups -- stable across resets, per
Ruling E's fixed-checkpoint model.
"""

from config.kttl_v2_profiles import PILOT_PROFILE

DEMO_TRANSCRIPT_FILENAME = "KCTA_KT_Transcript_PBI_Dashboards.docx"

# Fixed v4-shaped UUIDs (36 chars, matches models.mixins.UUIDPrimaryKeyMixin's
# String(36) column) -- deliberately NOT generated via uuid.uuid4() at
# import time, so they are byte-identical across every process/run.
DEMO_PROGRAM_ID = "00000000-0000-4000-8000-0000000000d1"
DEMO_PACKAGE_ID = "00000000-0000-4000-8000-0000000000d2"

READY_PARTICIPANT_ID = "00000000-0000-4000-8000-0000000000d3"
CONDITIONALLY_READY_PARTICIPANT_ID = "00000000-0000-4000-8000-0000000000d4"
NOT_READY_PARTICIPANT_ID = "00000000-0000-4000-8000-0000000000d5"

DEMO_PROGRAM_NAME = "Analytics & Reporting Team — PBI Dashboard Handover (Hierarchical Demo)"
DEMO_PACKAGE_NAME = "Power BI Dashboard Maintenance Handover (Hierarchical)"

# The hierarchical pilot profile this demo package opts into
# (KnowledgePackage.kttl_profile_id). Re-exported here so callers don't
# need to know about config.kttl_v2_profiles directly.
DEMO_KTTL_PROFILE_ID = PILOT_PROFILE.profile_id

RECEIVER_NAMES: dict[str, str] = {
    READY_PARTICIPANT_ID: "Priya (Ready receiver)",
    CONDITIONALLY_READY_PARTICIPANT_ID: "Receiver B (Conditionally Ready)",
    NOT_READY_PARTICIPANT_ID: "Receiver C (Not Ready)",
}
