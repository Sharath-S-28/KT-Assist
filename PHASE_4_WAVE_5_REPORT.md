# Phase 4 — Wave 5 Report: Enrichment Coordination

Branch: `feature/kva-kge-hierarchical-assurance`

## Implementation Summary

Built the thin coordinator (Amendment's Option C, approved) that sequences prioritized Knowledge Gap → question → response interpretation → graph update → revalidation → status update, without absorbing any existing module's logic. Two small additive extensions to legacy modules (`response_interpretation.py`, `graph_update.py`) make attribute-level patching possible; both verified not to change any v1 call path. Full loop verified end-to-end, including partial resolution and unrelated-gap isolation.

## Files Created

- `services/coverage/enrichment_coordinator.py` — `generate_remediation_question`, `build_interpretation_from_attribute_answers`, `build_interpretation_from_new_object`, `revalidate_gap`, `run_enrichment_round`, `EnrichmentRoundResult`
- `tests/wave5/test_wave5_enrichment_coordination.py` — 13 tests

## Files Modified

- `services/assessment/response_interpretation.py` — `InterpretedObjectChange` gained `attribute_updates: Optional[dict]` and `target_gap_id: Optional[str]`, both defaulting `None` (additive)
- `services/graph/graph_update.py` — `apply_interpreted_changes()`'s "update" branch now merges `attribute_updates` into the target object's `attributes` dict when present; imports the state model needed for that. No change to its "create" branch or to any other function in the file.

## Tests Added

13 new: remediation-question reuse, both interpretation builders (positive + their guard-rail rejection of the wrong gap shape), attribute-merge-preserves-other-attributes, legacy-update-path-unaffected, revalidation (fully resolved / partially resolved-and-narrowed), two full end-to-end rounds (attribute-gap resolution, TYPE_GAP object creation), unrelated-gap isolation, confidence-absence check.

## Test Results

**609 passed, 1 skipped** (596 baseline + 13 new). **Zero regressions.**

## Blueprint Deviations

- **No Claude-assisted interpretation path built.** The legacy `interpret_gap_response()` supports an optional `claude_client` for AI-assisted interpretation; Wave 5's new builders (`build_interpretation_from_attribute_answers`, `build_interpretation_from_new_object`) are purely deterministic — they take an already-structured answer (a `{attribute_name: value}` dict, or explicit object_type/name), not raw free text needing AI interpretation. This matches the fixed scope's silence on Claude involvement and keeps Wave 5 fully offline/testable, but means a real UI would need its own step turning a human's free-text answer into that structured dict before calling these builders — not built here, and not part of the stated scope.
- **`run_enrichment_round` only revalidates the ONE gap it was given**, not the whole package. This is deliberate (matches "prioritized Knowledge Gap" — singular — in the fixed scope) but means a caller wanting a full closure loop (repeatedly pick top gap, resolve, re-rank, repeat) needs to write that loop themselves; it isn't provided as a function. Flagging since the legacy `WorkflowRunner.close_gaps_until_sufficient()` does provide that outer loop for v1 — an analogous wrapper for the new model would be a natural, small next step if wanted.

## Technical Risks

- Revalidation re-runs full detection (`build_validation_plan` + `detect_all_findings`) over the whole graph on every round rather than incrementally checking just the affected object — correct, but potentially wasteful at large package sizes. Not a concern at pilot scale (3 object types, small graphs); worth profiling before this scales up.
- `KnowledgeGap(**{**gap.__dict__, ...})` (used to produce an updated copy with new status/findings) relies on `KnowledgeGap` staying a plain dataclass with no `__post_init__` side effects — fine today, but a maintenance trap if the dataclass grows validation logic later. A `dataclasses.replace()` call would be more robust; used the dict-unpack form here only because `replace()` doesn't play well with the mutable default list already on `findings`. Worth revisiting if this pattern spreads.

## Recommendation for Next Wave

Transition Risk derivation is the natural next step now that Knowledge Gaps have real open/resolved status — a Risk Mapping Rule can key off which Knowledge Gaps remain open after enrichment. Still explicitly not started per this wave's scope.
