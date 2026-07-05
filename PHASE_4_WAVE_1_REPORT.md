# Phase 4 — Wave 1 Report: Foundation & Regression Protection

Branch: `feature/kva-kge-hierarchical-assurance` (off `main`)

## 1. Implementation Summary

Built the deterministic foundation Wave 1 scoped: canonical domain models (`KnowledgeElementState` + lightweight `AttributeValue`/`RelationshipAssertion`/`EvidenceRequirement`, `Finding`/`KnowledgeGap`/`GapBundle`/`TransitionRisk`), the ontology registry, `KTTLProfileV2` + v1-compatibility loader, and the `ValidationPlan` builder. `KnowledgeObject`/`Relationship` extended additively. Legacy `GapCandidate` untouched; a one-way `finding_from_gap_candidate()` adapter proves the compatibility boundary. Nothing in production wiring (coverage engine, gap detection, KVA) calls any of this yet — all net-new, dormant code paths, per Wave 1 scope.

## 2. Files Created

- `schemas/knowledge_element_state.py` — `KnowledgeElementState` enum, `AttributeValue`, `AttributeEvidence`, `RelationshipAssertion`, `EvidenceRequirement`
- `schemas/gap_model.py` — `Finding`, `KnowledgeGap`, `GapBundle`, `TransitionRisk`, `finding_from_gap_candidate()`
- `schemas/validation_plan.py` — `ValidationPlan`, `EvaluatedRequirement`
- `schemas/kttl_profile.py` — `KTTLProfileV2`, `load_v1_compatible()`
- `config/ontology.py` — `ObjectTypeSpec`, `OBJECT_TYPE_SPECS` (all 9 types), `get_object_type_spec()`
- `services/coverage/validation_plan_builder.py` — `build_validation_plan()`
- `tests/regression/test_v1_baseline_lock.py`, `tests/wave1/test_hierarchical_assurance_foundation.py`

## 3. Files Modified

- `schemas/knowledge_graph.py` — `KnowledgeObject` +`schema_version`, `attributes`, `validation_status`, `evidence_refs` (all defaulted); `Relationship` +`state` (defaults `PRESENT`), `provenance`. No existing field changed or removed.

## 4. Tests Added

21 new tests: 3 regression-lock (dataset coverage numbers, golden-response set, full-workflow worked example) + 18 covering Wave 1's required checks 6–15 (legacy/new `KnowledgeObject` round-trips, all 5 states round-tripping across all 3 structures, adapter correctness, `ValidationPlan` determinism, conditional-attribute inclusion, deterministic `NOT_APPLICABLE` exclusion, confidence-absence in the builder, ontology completeness).

## 5. Test Results

- Baseline (before any change): **517 passed, 1 skipped**
- After Wave 1: **538 passed, 1 skipped** (517 + 21 new, zero regressions)
- Invariants suite specifically: **11/11 passed**, including Claude-never-scores

## 6. Blueprint Deviations

- **Pilot object types don't exist yet.** The blueprint's Section 9 KAI pilot names System, Exception, Recovery Procedure. Only System is in `config.KNOWLEDGE_OBJECT_TYPES` today. Adding the other two isn't a Wave 1 (or even pure-ontology) decision — `services/agents/kase_scoring.py` asserts `KNOWLEDGE_OBJECT_TYPES == OBJECT_TYPE_COMPETENCY_MAP.keys()` at import time, so adding object types touches KASE scoring immediately. **Recommend a ruling before Wave 2's KAI pilot**: either add Exception/Recovery Procedure as real object types (with competency-map entries), or rescope the pilot to existing types (System + a second type TBD). I did not decide this silently — `config/ontology.py`'s registry only fully populates System for now; the other 8 types have structurally-complete but empty entries.
- **`not_applicable_conditions` added to `ObjectTypeSpec`**, not explicitly named in the blueprint. Needed a concrete mechanism to satisfy required test #13 ("valid deterministic NOT_APPLICABLE excludes from the universe") distinctly from conditional-attribute inclusion (test #12). Both are now real, tested, and documented as distinct concepts in the module docstring.
- **Condition-language is intentionally minimal** — `_evaluate_condition()` in `validation_plan_builder.py` supports only `attribute == literal`. Sufficient to prove the mechanism per Wave 1's scope; a richer expression language is a Wave 2+ decision, not assumed here.

## 7. Technical Risks

- **Ontology authorship is unstarted for 8 of 9 types.** Structurally safe (empty = today's behavior) but means Wave 2's pilot can only meaningfully exercise System until more types are authored — expected, flagged, not blocking.
- **`_evaluate_condition`'s regex-based parser** will need to grow before real profiles use non-trivial conditions; worth deciding the ceiling for "minimal" before Wave 2 rather than organically expanding it.
- **No v2 profile is wired anywhere yet** — `KTTLProfileV2` instances in tests are hand-built, not loaded from any config/DB. This is correct for Wave 1 (no KTTL v2 authoring in scope) but Wave 2 needs a real decision on where v2 profiles will actually live.

## 8. Recommendation for Wave 2

Do not start structured KAI extraction until the Exception/Recovery Procedure ontology question (Section 6) is ruled on — it directly determines pilot scope. Suggest: rule on that first, then proceed to Wave 2 exactly as blueprinted (KAI structured extraction pilot → attribute arbitration), scoped to whichever object types get confirmed.
