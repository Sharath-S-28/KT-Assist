# Demo Runbook (Session 36)

This is the operational runbook for running a live stakeholder walkthrough of
KT Assist end to end, and for cleaning up afterward.

## What it shows

`python cli.py demo` drives one dedicated, single-package KT program through
the full lifecycle using the same worked example already proven by
`tests/level3/test_full_workflow.py` and `tests/test_demo_runner.py`:

- A Process / Task / Business Rule / Risk knowledge extraction from a
  month-end close SOP.
- Knowledge validation, which surfaces a `System` gap and a `Task` gap.
- Two gap closures (one creates a new System object, one updates the
  existing Task), raising coverage from 8.5/13 to 11.5/13 to 13/13.
- Assessment generation, scenario responses, and evidence scoring.
- OIS scoring and a final readiness decision (`Ready`, `Gold`).

It always runs in `DEV_MODE` (mocked extraction/boundary/relationship/LLM
calls, no live API spend), so it is safe to re-run on demand during a
walkthrough.

## Running the demo

```
python cli.py demo
```

This prints the full step-by-step narration (`[OK]` / `[BLOCKED]` lines) as
the walkthrough proceeds, and logs a final summary line with the step count
and `all_ok` flag.

**Two `[BLOCKED]` lines are expected and harmless**, not a sign anything is
broken:

1. The Gap Resolution entry guard reads the latest *persisted* `CoverageResult`,
   which does not exist yet the first time coverage is computed in-memory, so
   it reports the gate as failing even though the in-memory score already
   clears the threshold.
2. Re-entering "Knowledge Validation" from "Knowledge Validation" after gap
   closure is a same-state no-op edge that the lifecycle map correctly
   refuses as illegal, not a real transition.

Both are caught and narrated, never raised — the walkthrough still reaches
`Completed`.

## Why each run creates a new program

`cmd_demo` deliberately creates a brand-new `KTProgram`/`KnowledgePackage`/
`Participant` every time, rather than reusing a previous run's data. This is
intentional: `services/workflow_engine.py`'s guards (e.g.
`guard_validation_to_assessment`) evaluate every package across an entire
program, so running the demo against a program that already has other
packages in other states would produce spurious `[BLOCKED]` results that
have nothing to do with the walkthrough itself. A fresh, isolated
single-package program guarantees the happy path is what gets shown.

The cost of that design: every run leaves behind a full program's worth of
rows (knowledge graph versions, coverage results, gap records, assessment
packages, scenarios, scenario responses, evidence marker results, OIS
results, receiver readiness, workflow transition logs), and nothing in
`cmd_demo` cleans this up automatically — a live walkthrough is not the
place to silently delete data mid-demo.

## Cleaning up after a demo (or several)

```
python scripts/reset_demo.py            # delete every demo-runbook program
python scripts/reset_demo.py --dry-run  # report what would be deleted, change nothing
```

This finds every `KTProgram` named `cli.DEMO_PROGRAM_NAME` ("Demo — CLI
Runbook Walkthrough") and deletes it and every row transitively rooted at it,
table by table, bottom-up.

It does this with explicit per-table deletes rather than a single
`session.delete(program)`, because no ORM cascade in this codebase reaches
past `KnowledgePackage`/`Participant` — a naive cascading delete would either
raise `IntegrityError` under SQLite foreign-key enforcement or silently
orphan rows. See `scripts/reset_demo.py`'s module docstring for the full
ruling and the exact table order.

Typical workflow for a walkthrough session:

```
python cli.py demo               # run the walkthrough for stakeholders
# ... repeat as many times as needed ...
python scripts/reset_demo.py     # clean up all demo programs when done
```

`--dry-run` is safe to run at any time to check how much demo clutter has
accumulated without changing anything.
