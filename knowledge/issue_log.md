# KT-Assist — Issue Log

## Active Issues / Features
| ID | Item | Owner | Status |
|---|---|---|---|
| A1 | Phase 13 datasets D1–D3 + D8 (denominator-first, backward-engineered) | Claude | In progress — unblocked by A5 |
| A2 | Phase 12 unified invariants suite — collapse Phase 9–11 guards into one CI gate | Claude | In progress |
| A6 | Repo hygiene: `.gitignore` runtime artifacts (`assets/<uuid>/`, `*.db.bak`, `tmp_cache_dbg`, `graphs_smoketest`); remove `zz_debug_test*`, `test_demo_runner_copy`, empty stubs | Claude | Proposed |

## Closed Issues History

6. **Ruling A3 — At-risk predicate (KT Program level, Executive Dashboard).** Proposed by Claude, approved by Sharath 2026-07-04. `At-Risk = (any package Coverage < 85%) OR (any required receiver Readiness = Not Ready) OR (any unresolved High-Risk Open Gap)`. Pure boolean over already-computed values, Python-only, no new scoring path. Implement in `services/reporting/executive_dashboard_service.py`.

7. **Ruling A4 — Competency warning band (Screen 8 Pass/Fail/Warning indicator).** Proposed by Claude, approved by Sharath 2026-07-04. `Fail < 70` (unchanged critical gate), `Warning 70–79`, `Pass ≥ 80`. Implement in `config/scoring.py` as named constants, consumed by `services/agents/kase_scoring.py` and Screen 8.

8. **Ruling A5 — D8 pillar scoring method.** Proposed by Claude, approved by Sharath 2026-07-04. Canonical method is **weighted intra-pillar scoring (S26 locked decision)**, using Chunk 3's competency weighting model normalized within each pillar (per-pillar competency weights already sum to that pillar's OIS weight, e.g. 12+10+13=35 = Operational Execution). The Chunk 6 Stage-5 example (simple average) is illustrative only, not authoritative. Phase 13 D8 ground truth must be backward-engineered against the weighted formula. Implement/verify in `services/agents/kase_scoring.py`.
1. **Bug #1 — lifecycle_state desync** (commit `ed3019d`). Executive Dashboard showed "Draft/Not Assessed" after full pipeline because `DemoRunner.run_all()` never advanced program lifecycle. **Fix:** lifecycle now advances **through HTTP endpoints** (not direct service mutation), keeping DemoRunner faithful to real user flow. Files: `services/orchestration/demo_runner.py`, routers, Screen 1. **Why:** HTTP-only guard means the demo must exercise the same path users do.

2. **`domain_breakdown_json` always null in Validation Center.** No code path persisted `CoverageResult` from a live `run_kva()`. **Fix:** created `services/coverage/coverage_persistence.py` as a **leaf shared module** (breaks `graph_update` ↔ `workflow_runner` circular import) and extended the upload endpoint to run `validate()` + `persist_coverage_result()` after `ingest()`. **Why leaf module:** embedding persistence in either orchestration or graph_update reintroduced the cycle.

3. **Stale `graph_version_id` in DemoRunner.** After gap closure advanced graph v1→v2, DemoRunner kept passing v1, corrupting downstream reads. **Fix:** re-read current version post-mutation. Established convention: never cache graph version across mutations. Files: `services/orchestration/demo_runner.py`, `services/graph/graph_update.py`.

4. **`close_gap()` computed but never persisted `KVAResult`.** Every gap response recomputed coverage then discarded it. **Fix:** persist via `coverage_persistence` inside `services/coverage/gap_governance.py`. Discovered (like #2) only by **chaining HTTP calls end-to-end** — codified as a testing principle.

5. **Structural refactor + spec reconciliation.** Flat `services/` → 8 domain subpackages (`a111da7`), dead flat duplicates removed (`469671c`), `config.py` monolith → `config/` package (`bf9e929`); orphaned shadowed `config.py` and duplicate root `frameworks/`/`prompts/` removed 2026-07-04. Spec side (via Cowork): competency catalog reconciled to **12 OIF competencies / 4 pillars** with correct weights + critical flags; KTTL template profiles fixed to exact required/optional object sets per package type. **Why:** Master Spec v2 is the reconciliation authority; code follows spec, never the reverse.
