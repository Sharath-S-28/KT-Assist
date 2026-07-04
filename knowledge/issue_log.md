# KT-Assist — Issue Log

## Active Issues / Features
| ID | Item | Owner | Status |
|---|---|---|---|
| A1 | Phase 13 datasets D1–D3 + D8 (denominator-first, backward-engineered; blocks Phase 12 golden E2E) | Claude | In progress |
| A2 | Phase 12 unified invariants suite — collapse Phase 9–11 guards into one CI gate | Claude | In progress |
| A3 | Ruling: at-risk predicate definition | Sharath | Open |
| A4 | Ruling: competency warning band | Sharath | Open |
| A5 | Ruling: D8 pillar scoring — weighted S26 method vs Chunk-6 simple-average | Sharath | Open |
| A6 | Repo hygiene: `.gitignore` runtime artifacts (`assets/<uuid>/`, `*.db.bak`, `tmp_cache_dbg`, `graphs_smoketest`); remove `zz_debug_test*`, `test_demo_runner_copy`, empty stubs | Claude | Proposed |

## Closed Issues History
1. **Bug #1 — lifecycle_state desync** (commit `ed3019d`). Executive Dashboard showed "Draft/Not Assessed" after full pipeline because `DemoRunner.run_all()` never advanced program lifecycle. **Fix:** lifecycle now advances **through HTTP endpoints** (not direct service mutation), keeping DemoRunner faithful to real user flow. Files: `services/orchestration/demo_runner.py`, routers, Screen 1. **Why:** HTTP-only guard means the demo must exercise the same path users do.

2. **`domain_breakdown_json` always null in Validation Center.** No code path persisted `CoverageResult` from a live `run_kva()`. **Fix:** created `services/coverage/coverage_persistence.py` as a **leaf shared module** (breaks `graph_update` ↔ `workflow_runner` circular import) and extended the upload endpoint to run `validate()` + `persist_coverage_result()` after `ingest()`. **Why leaf module:** embedding persistence in either orchestration or graph_update reintroduced the cycle.

3. **Stale `graph_version_id` in DemoRunner.** After gap closure advanced graph v1→v2, DemoRunner kept passing v1, corrupting downstream reads. **Fix:** re-read current version post-mutation. Established convention: never cache graph version across mutations. Files: `services/orchestration/demo_runner.py`, `services/graph/graph_update.py`.

4. **`close_gap()` computed but never persisted `KVAResult`.** Every gap response recomputed coverage then discarded it. **Fix:** persist via `coverage_persistence` inside `services/coverage/gap_governance.py`. Discovered (like #2) only by **chaining HTTP calls end-to-end** — codified as a testing principle.

5. **Structural refactor + spec reconciliation.** Flat `services/` → 8 domain subpackages (`a111da7`), dead flat duplicates removed (`469671c`), `config.py` monolith → `config/` package (`bf9e929`); orphaned shadowed `config.py` and duplicate root `frameworks/`/`prompts/` removed 2026-07-04. Spec side (via Cowork): competency catalog reconciled to **12 OIF competencies / 4 pillars** with correct weights + critical flags; KTTL template profiles fixed to exact required/optional object sets per package type. **Why:** Master Spec v2 is the reconciliation authority; code follows spec, never the reverse.
