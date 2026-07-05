# ADR 0001: Deferred canonical ontology expansion for Exception and Recovery Procedure

**Status:** Deferred (not decided). **Date:** Wave 2, Phase 4, Hierarchical Knowledge Assurance redesign.

## Context

The Phase 3 Implementation Blueprint's structured-KAI pilot (Section 9) named three object types: System, Exception, and Recovery Procedure. Only System exists in `config.KNOWLEDGE_OBJECT_TYPES` today. Exception and Recovery Procedure do not.

`config.KNOWLEDGE_OBJECT_TYPES` is coupled to KASE scoring: `services/agents/kase_scoring.py` asserts (at import time) that `set(config.OBJECT_TYPE_COMPETENCY_MAP) == set(config.KNOWLEDGE_OBJECT_TYPES)`. Adding a new object type is therefore never an ontology-only change — it immediately requires a corresponding competency-map entry and touches KASE's scoring surface.

## Decision

For Wave 2, **do not add Exception or Recovery Procedure to `KNOWLEDGE_OBJECT_TYPES`**, and **do not modify KASE's competency mapping**. The structured-KAI pilot instead uses three existing types — **System, Known Issue, Task** — with pilot-only attribute schemas (`config/ontology.py`):

- Known Issue's pilot schema (`trigger`, `impact`, `detection_method`, `resolution_path`, `escalation_condition`) is deliberately similar in spirit to what an "Exception" type might look like, but is **not** declared equivalent to one.
- Task's pilot schema (`trigger_condition`, `execution_steps`, `responsible_role`, `validation_criteria`) is similarly adjacent to a "Recovery Procedure" concept, but is likewise **not** declared equivalent.

This is a scope substitution for the pilot only, not a resolution of whether Exception/Recovery Procedure should eventually exist as first-class types.

## Consequences

- The pilot can proceed without touching KASE at all, keeping Wave 2 additive and low-risk.
- The real question — should Exception and Recovery Procedure become canonical object types — remains open. Answering it requires deciding, at minimum: the competency-map entries for two new types, whether existing Known Issue/Task data should ever be reclassified, and whether the pilot's Known Issue/Task attribute schemas would carry over or be superseded.
- **The `KNOWLEDGE_OBJECT_TYPES` ↔ `OBJECT_TYPE_COMPETENCY_MAP` coupling itself is noted here as a standing architectural concern**, independent of this specific ontology question: any future object-type addition, for any reason, will hit the same assertion. Whether that coupling should be loosened (e.g. allowing object types with no competency mapping) is a separate decision, also not resolved by this ADR.

## Not decided here

- Whether Exception and Recovery Procedure will ever be added.
- Whether Known Issue/Task's pilot schemas would be reused, renamed, or discarded if/when those types are added.
- Whether the `KNOWLEDGE_OBJECT_TYPES`/KASE coupling should change.

Revisit when there is a concrete driver (e.g. Wave 3+ needs a real Exception-like type with different competency weighting than Known Issue).
