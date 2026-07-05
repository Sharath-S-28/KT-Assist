# KT-Assist — Current State

```yaml
last_agent: Claude
status: Wave 2 (structured KAI extraction pilot) complete on feature/kva-kge-hierarchical-assurance
```

## 0. feature/kva-kge-hierarchical-assurance branch (in progress, not on main)
Hierarchical Knowledge Assurance redesign (separate initiative from `demo-mode`, which has its own unrelated PBI-transcript demo-seeding work — do not conflate). Phases 1–3 (root-cause analysis, target architecture, Amendment Round 1, final rulings, Phase 3 Implementation Blueprint) were design-only, delivered as files, not committed to any branch.
- **Wave 1 (Foundation & Regression Protection): complete.** `KnowledgeElementState` model (+`AttributeValue`/`RelationshipAssertion`/`EvidenceRequirement`), `Finding`/`KnowledgeGap`/`GapBundle`/`TransitionRisk` schemas, ontology registry (`config/ontology.py`, all 9 types structurally present, System fully authored), `KTTLProfileV2` + v1-compat loader, `ValidationPlan` builder (`services/coverage/validation_plan_builder.py`). `KnowledgeObject`/`Relationship` extended additively (`schema_version`, `attributes`, `validation_status`, `evidence_refs`, `state`, `provenance`). Legacy `GapCandidate` untouched; `finding_from_gap_candidate()` is the one-way compatibility adapter. Nothing in production wiring calls any of this yet.
- Tests: 538 passed, 1 skipped (517 baseline + 21 new), zero regressions. Full detail in `PHASE_4_WAVE_1_REPORT.md`.
- **Open question before Wave 2**: blueprint's KAI pilot names Exception/Recovery Procedure, neither in `KNOWLEDGE_OBJECT_TYPES` today; adding them touches KASE's `OBJECT_TYPE_COMPETENCY_MAP` assertion. Needs a ruling — see report §6.
- Not yet started: KAI structured extraction pilot, arbitration changes, new Finding detectors, KCS/KQS, consolidation, prioritization, enrichment coordination, transition-risk derivation, KAR, persistence migration, API changes (all later waves).
- **Wave 2 (Structured KAI Extraction Pilot): complete.** System/Known Issue/Task pilot schemas authored in `config/ontology.py`; `PILOT_PROFILE` v2 KTTL profile (`config/kttl_v2_profiles.py`); `services/agents/attribute_arbitration.py` (Python-owned final state assignment: merge/CONFLICTING/deterministic-N/A/NOT_OBSERVED); shared `services/coverage/condition_evaluator.py` (unsupported syntax now fails visibly, not silently false); `kai_extraction.py` extended opt-in only (`pilot_object_types` payload key) — legacy path fully byte-identical when absent. ADR `docs/adr/0001-...` records Exception/Recovery Procedure deferred, `KNOWLEDGE_OBJECT_TYPES` and KASE map both unchanged (tested). 558 passed/1 skipped (538+20), zero regressions. Real bug found+fixed this wave: N/A/conditional attribute evaluation order now independent of input order. See `PHASE_4_WAVE_2_REPORT.md`.
- **Open before Wave 3**: cross-chunk attribute merge is proven correct in isolation but not wired into the live ingestion pipeline (only the existing object-level boundary-check merge runs live); prompt reliability untested against a real Claude call (this environment is DEV_MODE/mock-only throughout). Recommend resolving one of these before starting Finding detectors.

## 1. Current Milestone / Active Task
- Phase 12↔13 boundary. Sessions S1–S36 (Phases 1–12) specified; core pipeline implemented and E2E-tested via DemoRunner.
- Phase 13 D1–D3+D8 (`datasets/power_bi_dashboard/` + `datasets/golden/`): **confirmed already complete 2026-07-04**, not new work — 8/8 dataset tests pass. D4–D7 (Datasets 2/3) explicitly out-of-scope for this build pass, per `manifest.json`. See issue_log.md #11.
- Phase 12 **unified invariants suite: CLOSED 2026-07-04.** All three guards (Phase 9 number-guard, Phase 10 no-rescore, Phase 11 HTTP-only import) now live in `tests/invariants/test_architectural_boundaries.py`. Full suite: 518 passed, 1 skipped.
- DemoRunner golden values frozen: coverage **63%→89%**, **OIS 84**, **READY/Silver** — treat as regression contract. Independent of the Phase 13 dataset (71.05%→86.84%) — two separate fixtures, not a conflict.
- Real-transcript validation done: `KCTA_KT_Transcript_PBI_Dashboards.docx` → 9 chunks, 36 objects, KTTL auto-detected "Dashboard".
- **Only remaining open item: A6** (repo hygiene).

## 2. Pain Points / Technical Debt
- Rulings A3–A5 resolved 2026-07-04 (see issue_log.md #6–8) — all three were already implemented in shipped code before this session; the issue log was stale. No open rulings remain.
- Windows compatibility (A7, closed 2026-07-04): `Path.read_text()` must always pass `encoding="utf-8"` explicitly (Windows defaults to CP1252); cache keys must never contain raw `:` in filenames. Watch for the same pattern in any new file-reading code.
- Circular-import-prone service layer — mitigated by leaf modules (`coverage_persistence.py`); keep persistence out of orchestration/graph services.
- Repo hygiene resolved 2026-07-04 (A6): ~1,400 pre-existing committed runtime artifacts untracked (`assets/<uuid>/`, `data/*.db.bak`, `data/graphs_smoketest/`, `data/tmp_cache_dbg/`, `data/.fuse_hidden*`); 3 dead test files (`tests/zz_debug_test*.py`, `tests/test_demo_runner_copy.py`) and 3 empty stub files (`agents/__init__.py`, `storage/__init__.py`, `models/__init__placeholder__.py`) removed. No open pain points remain.
- SQLite WAL = single-writer; fine for single-user internal tool, a constraint for any future multi-user work.
- No auth layer (by design, internal). Do not assume or add auth.
- Streamlit rerun/session-state model is fragile — keep state server-side; React migration planned at API boundary only.

## 3. Strict Rules & Conventions (violations fail CI)
1. **All scoring in Python** (coverage, competency, pillar, OIS, gates, readiness). Claude API = extraction, generation, evidence detection, narrative **only**.
2. **Master Spec v2 is frozen authority** — any divergence resolves in favor of the frozen document. Annotate `[FROZEN]` vs `[PROPOSAL]` in all specs.
3. **Frontend is HTTP-only** via `frontend/api_client.py`; never import services into `frontend/`.
4. **No magic numbers** outside `config/` package.
5. **Graph is versioned** — never reuse a `graph_version_id` across a mutation; re-read after gap closure.
6. Persistence lives in **dedicated leaf modules**, not orchestration/graph services.
7. KAI mocks respect real prompt boundaries: **one chunk per mock call, no cross-chunk bleed**.
8. Cost controls always on: KAI cache, scenario cache, dev-mode mocks, batched boundary checks (10 objects/call).
9. Empty recommendations on "Conditionally Ready" is **correct** (engine fires only on individual critical-competency gate failure) — not a bug.
10. Frozen palette: `#161916 #282A27 #444744 #6D706B #FFFFFF #FFFAF4 #FFF2DF #FF4F59 #FFAD28 #3D6B4F`.
11. Discover integration bugs by **chaining HTTP calls end-to-end**, not isolated unit calls.
12. Each phase spec ends with a "What to confirm" section separating Sharath rulings from Claude proposals.
13. At-Risk (KT Program, Executive Dashboard) = readiness != Ready AND (program mean coverage < `COVERAGE_SUFFICIENCY_THRESHOLD` OR any package has a failing critical competency OR any package has an open High-risk gap). See `executive_dashboard_service.py`.
14. Competency indicator bands (asymmetric): critical competencies — Fail < 70, Warning 70–74, Pass ≥ 75; non-critical competencies — Warning < 70, Pass ≥ 70 (no Fail state). See `readiness_dashboard_service.py`.
15. Pillar score = weighted intra-pillar average using Chunk 3's competency weights normalized per pillar (not a simple average). See `kase_scoring.py`.
