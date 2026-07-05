# Phase 4 — Wave 2 Report: Structured KAI Extraction Pilot

Branch: `feature/kva-kge-hierarchical-assurance`

## Implementation Summary

Extended KAI extraction for three existing object types (System, Known Issue, Task) to propose structured attribute values + states, gated entirely behind an opt-in `pilot_object_types` parameter so legacy extraction is untouched when it's absent. Built attribute-level arbitration as a pure, independently-testable module: Python owns final state assignment (merge agreeing values, detect conflicts, evaluate deterministic NOT_APPLICABLE, finalize NOT_OBSERVED for unaddressed applicable attributes). Condition evaluation was extracted into one shared module used by both `ValidationPlan` construction and arbitration, and now fails visibly (a typed exception, recorded in diagnostics) on unsupported syntax instead of silently returning false. One real pilot v2 KTTL profile created, stored as configuration code. ADR written documenting the deferred Exception/Recovery Procedure ontology question and the underlying `KNOWLEDGE_OBJECT_TYPES`↔KASE coupling as a standing concern, not resolved here.

## Files Created

- `services/coverage/condition_evaluator.py` — shared `evaluate_condition()`, `UnsupportedConditionSyntaxError`
- `services/agents/attribute_arbitration.py` — `ProposedAttribute`, `arbitrate_attributes()`, `ArbitrationDiagnostics`
- `config/kttl_v2_profiles.py` — `PILOT_PROFILE` (System + Known Issue + Task)
- `docs/adr/0001-deferred-exception-recovery-procedure-ontology.md`
- `tests/wave2/test_wave2_pilot.py`

## Files Modified

- `config/ontology.py` — added Known Issue and Task pilot attribute specs (mandatory/conditional attributes, N/A conditions, rule-family map); updated module docstring for the Wave 2 ruling.
- `services/coverage/validation_plan_builder.py` — now imports the shared condition evaluator instead of a private copy; unsupported syntax recorded in `ValidationPlan.unsupported_conditions` rather than silently treated as false.
- `schemas/validation_plan.py` — added `unsupported_conditions` field.
- `services/agents/kai_extraction.py` — added `build_pilot_system_prompt()`, pilot-aware cache key (schema-version segment, pilot-only), `_parse_pilot_attributes()`; `KAIAgent.execute()` extended with an opt-in `pilot_object_types`/`extraction_run_id` payload key. `build_system_prompt()` itself is untouched.

## Tests Added

20 new tests covering all 17 required checks (some split into more than one test for clarity): structured extraction per pilot type, legacy-path non-interference, PRESENT+provenance, EXPLICITLY_UNKNOWN, NOT_OBSERVED finalization, N/A rejection without deterministic confirmation, N/A acceptance with it, cross-chunk CONFLICTING with no value loss, provenance survival, unsupported-syntax visibility (two tests — direct evaluator + surfaced during arbitration), reproducibility, cache-key schema-version behavior, full regression + invariants green, `KNOWLEDGE_OBJECT_TYPES` and KASE map unchanged.

## Test Results

- **558 passed, 1 skipped** (538 Wave-1 baseline + 20 new), **zero regressions**
- Invariants suite: unaffected (not re-run standalone this wave; covered inside the regression sweep in `test_full_regression_and_invariants_green`, which passed)

## Pilot Extraction Observations

- **Ordering bug found and fixed during this wave**: a deterministic N/A condition (e.g. `access_path` depends on `access_controlled`) only resolved correctly when the dependency attribute happened to be processed first. Since Claude's JSON response order isn't guaranteed to match dependency order, this was a real, silent-failure-prone bug, not a hypothetical one — caught by manual sanity testing before it reached the formal suite. Fixed by processing condition-independent attributes before condition-dependent ones, regardless of input order; verified with a reversed-order test.
- Claude is structurally prevented from asserting `NOT_OBSERVED` or `CONFLICTING` (`CLAUDE_PROPOSABLE_STATES` only allows PRESENT/EXPLICITLY_UNKNOWN/NOT_APPLICABLE) — enforced by dropping any other proposed value to NOT_OBSERVED defensively, both in `_parse_pilot_attributes()` and in arbitration.
- The three pilot schemas (System, Known Issue, Task) as specified worked cleanly against the deterministic-condition model with no schema changes needed.

## Blueprint Deviations

- **Cross-chunk identity/merge is not wired into the live pipeline.** `arbitrate_attributes()` is a pure function proven correct via direct unit tests (including a genuine cross-chunk conflict scenario), but nothing in `KAIAgent`/`arbitrate_objects()` currently groups same-identity objects across chunks and calls it automatically — that grouping today only exists via the separate boundary-check pass's explicit `merge_with` verdicts, which Wave 2 did not touch (modifying it risked the "preserve existing object-level arbitration behavior" requirement for zero justified benefit at pilot scale). Recommend wiring this as an explicit, reviewed step in Wave 3 rather than folding it in here.
- **Pilot object types are System/Known Issue/Task**, not System/Exception/Recovery Procedure per the original blueprint — per this wave's own ruling, with the ADR recording why.

## Technical Risks

- The ordering fix (independents-before-dependents) is a heuristic based on the ontology's declared dependency set; it hasn't been tested against a genuinely circular or multi-hop dependency chain (none exist in the pilot schemas, but a future object type might introduce one — would need a real topological sort, not this simpler split, if that happens).
- `_parse_pilot_attributes()` and `arbitrate_attributes()` are currently two separate defensive layers against a malformed Claude state proposal (both check `CLAUDE_PROPOSABLE_STATES`). This is intentional belt-and-suspenders for a pilot, but worth consolidating into one authority if this expands past three object types.
- No live Claude API call was exercised in these tests (this whole environment runs in `DEV_MODE`/mock-response mode throughout, consistent with the rest of the project) — the prompt text itself (`build_pilot_system_prompt`) has not been validated against a real model's actual output reliability, only against hand-authored mock responses shaped the way the prompt asks for. That reliability question is exactly what a real pilot run (outside this environment) would need to answer before Wave 3 expands scope.

## Recommendation for Wave 3

Do not expand the ontology to more object types yet. Before that, either (a) run this pilot against a real Claude extraction call on real transcripts to validate prompt reliability (the one thing this environment cannot test), or (b) if proceeding on trust, wire the cross-chunk merge integration flagged above so the mechanism is exercised end-to-end through the actual ingestion pipeline, not just through direct unit tests. Either is a reasonable next step; recommend against starting Finding detectors (the blueprint's next architectural layer) until one of these two is resolved, since Finding detection will consume whatever `arbitrate_attributes()` produces and inherits any reliability gap silently.
