# Phase 4 — Wave 7 Report: Final Integration & Rollout

Branch: `feature/kva-kge-hierarchical-assurance`

## Implementation Summary

Wired the hierarchical path end-to-end behind a single opt-in gate (`KnowledgePackage.kttl_profile_id`), added persistence for the new dimensional/gate data, exposed it through 4 new read-only API endpoints, and verified rollback, legacy-vs-hierarchical independence, and the full regression suite. The v1 path — every existing router, `WorkflowRunner` method, model field, and score — is untouched; every change in this wave is additive.

## Files Created

- `scripts/migrate_wave7_hierarchical_columns.py` — idempotent manual migration (no Alembic in this repo)
- `services/coverage/knowledge_assurance_persistence.py` — `persist_knowledge_assurance_result()`
- `schemas/hierarchical.py` — API read contracts (`KnowledgeAssuranceResultRead`, `KnowledgeGapRead`, `TransitionRiskRead`, `ClosureStatusRead`)
- `services/routers/hierarchical.py` — 4 endpoints: `GET /{id}/kar`, `/knowledge-gaps`, `/transition-risks`, `/closure-status`
- `tests/wave7/test_wave7_integration_and_rollout.py` — 15 tests

## Files Modified

- `models/coverage.py` — `CoverageResult` +9 nullable columns (kcs/tc/ac/rc/kqs/os/ev scores, quality_gate_applicable, quality_gate_passed)
- `models/program.py` — `KnowledgePackage` +nullable `kttl_profile_id` (the entire v2 opt-in gate)
- `services/orchestration/workflow_runner.py` — +3 methods (`ingest_hierarchical`, `validate_hierarchical`, `run_hierarchical_closure`) + `resolve_v2_profile_for_package`/`HIERARCHICAL_PROFILE_REGISTRY`; zero existing methods changed
- `app.py` — mounted the new router alongside every existing one

## Tests Added

15 new: end-to-end hierarchical workflow (2, including one reaching multiple closure rounds), API contracts (5: KAR 404/200, knowledge-gaps, transition-risks, closure-status, legacy-router-unaffected), legacy-vs-hierarchical comparison (1), rollback verification (3: profile cleared → ValueError + legacy path still works, same via API → 404, unregistered profile-id falls back safely), persistence (2: hierarchical columns populate, legacy rows stay NULL), confidence-absence (1).

## Test Results

**653 passed, 1 skipped** (638 baseline + 15 new). **Zero regressions.** Invariants suite: **11/11**.

## Migration Verified Against a Real Pre-Existing Database

Not just unit-tested — ran the migration script against a hand-built legacy-shaped SQLite file (old column set, one populated row), confirmed: all 10 new columns added, the existing row's data untouched (`coverage_score` intact, new columns NULL), and a second run was a true no-op (idempotent). Also caught and fixed a real issue in my own local dev DB, which pre-dated this wave's model changes — exactly the scenario this script exists for.

## Blueprint Deviations

- **No POST endpoint for submitting a structured answer over HTTP.** Read endpoints only (KAR, gaps, risks, closure status). Submitting an answer needs its own request-contract design — System/Known Issue/Task each expect different attribute names, so a generic `{attribute: value}` body is either unsafe (no validation against the right schema) or needs per-object-type request models, which is a real design task, not a gap to paper over. Advancing the closure loop today is in-process (`WorkflowRunner.run_hierarchical_closure`), exactly how Waves 5/6's tests already exercise it.
- **Knowledge Gaps/Transition Risks are not persisted, only computed on demand.** Both API endpoints and `validate_hierarchical()` recompute from the current graph each call rather than reading a stored table. This is deterministic and fast at pilot scale (confirmed by every test's timing), and avoids a second migration surface for gap/risk durability that wasn't asked for. Flagging as a reasonable scope boundary, not an oversight — if a caller needs to reference a *specific past* Knowledge Gap by a durable ID later, that's a real, separate feature.
- **`validate_hierarchical()` persists by default** (`persist=True`), unlike the legacy `validate()`, which never persists on its own (a caller must separately call `persist_coverage_result()`). Found this real API asymmetry while writing the persistence test — kept it as designed (persisting KAR by default is more useful for the API endpoints, which shouldn't require a second call), but noting the inconsistency with the legacy method's contract explicitly rather than silently.

## Real Bug Found and Fixed This Wave

`GraphPayload.graph_id` (the JSON payload's own identifier) is **not** the same value as the actual `KnowledgeGraphVersion` database row's primary key. My first pass at `validate_hierarchical()` used `payload.graph_id` as the FK value for `CoverageResult.graph_version_id` — worked fine until persistence was attempted against a real DB, where it failed with `FOREIGN KEY constraint failed`. Fixed by querying the actual `KnowledgeGraphVersion` row and using its real `.id`. Caught by an actual end-to-end run against a real database, not just unit tests with mocked persistence — worth noting as a reminder that DB-touching code needs at least one real-DB smoke test, not only unit tests against pure functions.

## Legacy-vs-Hierarchical Comparison

Verified directly (`test_legacy_vs_hierarchical_comparison_same_package_shape`): the same source text, ingested via `ingest()` into one package and `ingest_hierarchical()` into another, produces genuinely different result shapes — legacy stays a single `coverage_score` scalar with empty `attributes` dicts on every object; hierarchical produces populated `attributes`, TC/AC/RC/KCS dimensions, and a KQS/OS/EV family the legacy path has no concept of at all. Both ran independently without interfering with each other or the shared database.

## Rollback / Profile-Version Fallback — Verified

- Clearing `kttl_profile_id` on a previously-opted-in package: `validate_hierarchical()` raises `ValueError` (clear, not a crash), the API's `/kar` endpoint returns 404, and — critically — the **legacy `validate()` path still works against the exact same graph data**, proving rollback doesn't lose or corrupt anything.
- A `kttl_profile_id` pointing at an unregistered profile (simulating a future profile not yet deployed, or a typo) resolves to `None` via `resolve_v2_profile_for_package`, falling back safely rather than crashing.

## Pre-Demo Real Claude-Call Validation

**Cannot be completed in this environment** — no `ANTHROPIC_API_KEY` is configured here, consistent with this entire multi-wave engagement running in `DEV_MODE`/mock-response mode throughout. This is the one remaining external validation item before a live demo: whether `build_pilot_system_prompt()`'s actual instructions produce reliably-structured attribute/state responses from a real Claude call on real transcript text has never been tested against the live API, only against hand-authored mock responses shaped the way the prompt asks for. Recommend running the Wave 2 pilot (System/Known Issue/Task, using the real `KCTA_KT_Transcript_PBI_Dashboards.docx` transcript already available on the `demo-mode` branch) against a real API key before any live demonstration.

## Definition of Done — Status

- [x] All existing tests pass (653/653 non-skipped)
- [x] New invariant-adjacent checks pass (confidence-absence, 404 gating, legacy-unaffected)
- [x] v1 behavior unchanged (explicitly tested)
- [x] v2 profile generates a ValidationPlan / KAR / Findings / Gaps / Risks (all wired end-to-end)
- [x] Structured KAI pilot works for System/Known Issue/Task (Wave 2, re-exercised here)
- [x] Findings deterministic, consolidate into Knowledge Gaps, enrichment targets them, graph updates trigger revalidation (Waves 3-5, re-exercised here)
- [x] KCS/KQS from the shared ValidationPlan, Transition Risks rule-derived, KAR produced (Waves 3/6, re-exercised here)
- [x] KRA adapter works without changing KRA decision logic (Wave 6, re-exercised here)
- [x] KASE remains unaffected (never touched, any wave)
- [x] Legacy-vs-hierarchical comparison demonstrated
- [ ] **Real Claude-call validation** — blocked on API key availability, not on anything in this codebase

This is the final wave per the stated scope. No Wave 8 has been requested.
