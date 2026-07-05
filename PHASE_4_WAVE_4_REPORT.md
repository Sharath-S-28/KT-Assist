# Phase 4 — Wave 4 Report: Finding → Knowledge Gap Consolidation, Gap Bundles, Prioritization

Branch: `feature/kva-kge-hierarchical-assurance`

## Implementation Summary

Built consolidation (Finding → KnowledgeGap), cross-object bundling (KnowledgeGap → GapBundle), and risk-based prioritization — entirely reorganizational, no scoring math touched. Verified end-to-end against real detector output: a Task with two related missing attributes correctly merged into one KnowledgeGap; a System and a Task sharing the same remediation theme correctly bundled together across objects.

## Files Created

- `config/prioritization.py` — `PRIORITY_WEIGHTS` (3 active: criticality/readiness_blocking/aging; 4 inactive at zero weight, named for future activation)
- `services/coverage/consolidation.py` — `consolidate_findings()` (keys on (object_id, rule_family), never object_id alone), `bundle_knowledge_gaps()`
- `services/coverage/prioritization.py` — `compute_priority()`, `rank_gaps()`, `priority_tier()`, `rank_and_tier()`
- `tests/wave4/test_wave4_consolidation_and_prioritization.py` — 17 tests

## Files Modified

- `schemas/gap_model.py` — `KnowledgeGap` gained `created_at: Optional[datetime]` (additive, defaults `None`) for the aging factor

## Tests Added

17 new: consolidation grouping (same object/two families → two gaps; same object/family → one merged gap; different objects/same family → never merge; TYPE_GAP defaults), one end-to-end test via real detectors, 6 prioritization tests (criticality ordering, readiness-blocking reward, aging reward, status filtering, deterministic tie-break, inactive-factor-zero-weight check), 4 bundling tests (cross-object grouping, tier separation, non-open exclusion, score-immutability), 1 confidence-absence check.

## Test Results

**596 passed, 1 skipped** (579 baseline + 17 new). **Zero regressions.**

## Blueprint Deviations

- **Gap Bundle grouping uses `rule_family` as the operational_scenario value**, not a separate scenario taxonomy. The design docs describe `operational_scenario` as a distinct concept from `rule_family`, but the pilot ontology (`config/ontology.py`) has never defined one — only `rule_family_map` exists. Introducing a second, parallel taxonomy with no real content behind it would be inventing architecture in a wave explicitly scoped to say "no architecture changes." Documented in `consolidation.py`'s module docstring as a deliberate pilot-scope simplification. If/when a real scenario taxonomy is authored (e.g., "refresh-failure-recovery" spanning multiple rule_families), this is a one-function change (`bundle_knowledge_gaps`'s grouping key), not a schema change — `GapBundle.operational_scenario` already exists and is already populated, just with a coarser value than eventually intended.
- **Risk-level classification is new, Wave-4-local logic** (`consolidation._risk_level`), not a reuse of `config.GAP_RISK_MATRIX` — that matrix is keyed by the legacy 2-tier (Critical/Supporting) × (Missing/Partial) shape and doesn't fit the new 3-tier criticality × 5 gap_types combination. Same spirit, new table, clearly separated so nobody mistakes it for touching the legacy matrix.

## Technical Risks

- Every object in the pilot's test scenarios is Critical-criticality, so `compute_priority`'s differentiation was verified with hand-built KnowledgeGaps (Critical vs Important vs Supporting) rather than end-to-end — confirmed correct (0.85 / 0.333 / 0.167), but worth a real mixed-criticality package once one exists.
- Aging is structurally present but functionally inert until a persistence layer exists (still out of scope) — every gap's `created_at` is "now" at consolidation time within a single run, so the aging factor currently always contributes ~0. This is expected, not a bug, but means priority ordering today is really a 2-factor system (criticality + readiness_blocking) in practice.

## Recommendation for Next Wave

Enrichment coordination (gap → question → answer → graph update → revalidation) is the natural next step now that KnowledgeGaps and their priority ordering exist — it can consume `rank_gaps()`'s output directly to decide what to ask about first. Still explicitly not started per this wave's scope.
