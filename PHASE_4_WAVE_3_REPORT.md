# Phase 4 — Wave 3 Report: Five-Level Finding Detection, TC/AC/RC/OS/EV, KCS/KQS, Gates

Branch: `feature/kva-kge-hierarchical-assurance`

## Implementation Summary

Built the full detection + scoring layer Wave 3 scoped, entirely additive and independent of the v1 path (`coverage_engine.py`, `kva.py` untouched, zero calls into new code from either). All five Finding levels and all five score dimensions read from one shared `ValidationPlan` instance, so a package's Finding list and its score can never disagree about what was applicable. Extended `PILOT_PROFILE` with relationship/sufficiency/evidence requirements and dimension weights so all 5 levels are actually exercised, not just structurally present.

## Files Created

- `services/coverage/sufficiency_rules.py` — 2 pilot rules (`known_issue_min_viable_v1`, `task_min_viable_v1`), versioned registry
- `services/coverage/finding_detectors.py` — `detect_type_gaps` (reuses `coverage_engine._validate_type_status` exactly), `detect_attribute_gaps`, `detect_relationship_gaps`, `detect_operational_sufficiency_gaps`, `detect_validation_gaps`, `detect_all_findings`
- `services/coverage/dimensional_scoring.py` — `compute_tc/ac/rc/os/ev`, `compute_kcs`, `compute_kqs` (N/A renormalization), `evaluate_gates` (Sufficiency + Quality gates)
- `tests/wave3/test_wave3_scoring_and_findings.py` — 19 tests

## Files Modified

- `config/kttl_v2_profiles.py` — `PILOT_PROFILE` gained `relationship_requirements` (System→DEPENDS_ON), `sufficiency_rules`, `evidence_requirements` (Known Issue), and `weights` (wTC/wAC/wRC/wOS/wEV)
- `services/coverage/finding_detectors.py`, `dimensional_scoring.py`, `sufficiency_rules.py` — minor docstring rewording (see Blueprint Deviations)
- `tests/wave2/test_wave2_pilot.py` — removed one test (see Technical Risks)

## Tests Added

19 new: 2 per detector level (positive/negative), 1 fully-sufficient-package test (zero Findings, both gates pass), 3 dimension-formula tests, 2 KCS/KQS renormalization tests, 2 v1-structural-guarantee tests (v1 profile produces only TYPE_GAP Findings; Quality Gate never applicable for v1), 1 confidence-absence check, plus the fully-sufficient end-to-end case.

## Test Results

**579 passed, 1 skipped** (561 prior baseline − 1 removed + 19 new). **Zero regressions.**

## Blueprint Deviations

- **Gate blocking logic is object-criticality-based, not KnowledgeGap-based.** The blueprint's original gate design assumed Findings would already be consolidated into KnowledgeGaps (with their own criticality/risk_level) before gating — but consolidation is explicitly out of Wave 3 scope. Gates here instead derive "blocking" directly: a TYPE_GAP blocks if the type is required; any other Finding blocks if its object's criticality is Critical. This reproduces the v1 gate's spirit (required-type-missing is always blocking) without waiting for consolidation, which arrives in a later wave.
- **Quality Gate threshold is a placeholder.** Reuses `COVERAGE_SUFFICIENCY_THRESHOLD` (0.85) rather than a separately-tuned number — nobody has ruled on whether OS/EV should have their own bar. Flagged, not decided.
- **Two docstring rewordings** (in `finding_detectors.py`, `dimensional_scoring.py`, `sufficiency_rules.py`) — the literal word "confidence" in a module's own "we never reference this" disclaimer tripped that same module's grep-based invariant test. Reworded to avoid the substring; behavior unchanged, caught immediately since I wrote the module and its test in the same pass.

## Technical Risks

- **Found and fixed a real bug this wave**: `tests/wave2/test_wave2_pilot.py::test_full_regression_and_invariants_green` and my own new Wave 3 equivalent both spawned `pytest tests/` as a subprocess (excluding only their own directory). Once both existed, each one's subprocess run included the other's subprocess-spawning test, which included the first again — unbounded recursive nesting. Caught because the run took 3+ minutes and failed instead of the usual ~10-20 seconds. Removed both; full-suite verification is now done directly (as I've been doing throughout every wave), never as a self-referential test. Worth checking for this pattern before adding any future "run the whole suite" test.
- **`evaluate_gates`'s "blocking" definition is a reasonable interpretation, not a ruled decision** — it directly affects which packages pass/fail, so worth explicit confirmation before this feeds anything demo- or decision-facing.
- Sufficiency rules remain pilot-scope (2 rules, 2 object types) — same limitation flagged in Wave 2, unchanged.

## Recommendation for Wave 3+ / Next Steps

Consolidation (Finding → KnowledgeGap → GapBundle) and Transition Risk derivation are the natural next wave — once KnowledgeGaps exist, the gate logic above can be revisited to consume KnowledgeGap-level criticality instead of the object-criticality proxy used here, which would be a strict improvement, not a breaking change (the proxy already gives materially correct behavior for the pilot's 3 object types).
