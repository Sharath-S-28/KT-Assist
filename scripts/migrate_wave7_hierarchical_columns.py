"""
scripts/migrate_wave7_hierarchical_columns.py — manual migration for
existing databases (Phase 4 / Wave 7, Hierarchical Knowledge Assurance
redesign).

This repo has no Alembic/migration framework (documented risk since
Phase 3's blueprint). `Base.metadata.create_all()` only creates NEW
tables -- it does not add columns to `coverage_results` or
`knowledge_packages` if those tables already exist on disk. Any
database created fresh (e.g. every test run, a new demo DB) already has
every column below via the model definitions in models/coverage.py and
models/program.py; this script is only needed for a database that
existed BEFORE this wave.

Idempotent: checks each column's presence before adding it, so running
this twice (or against a fresh DB that already has everything) is a
no-op, not an error.

Usage:
    python3 scripts/migrate_wave7_hierarchical_columns.py [path/to/kt_assist.db]
    (defaults to config.DATABASE_PATH if no path given)

Rollback: drop the added columns, or simply stop writing to them --
every one is nullable and no existing v1 code path reads them, so their
mere presence is harmless. SQLite's DROP COLUMN support is
version-dependent, so the safer rollback is "stop using the columns,"
matching the Phase 3 blueprint's original rollback strategy.
"""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root, so `import config` works standalone

COVERAGE_RESULTS_COLUMNS = [
    ("kcs_score", "REAL"),
    ("tc_score", "REAL"),
    ("ac_score", "REAL"),
    ("rc_score", "REAL"),
    ("kqs_score", "REAL"),
    ("os_score", "REAL"),
    ("ev_score", "REAL"),
    ("quality_gate_applicable", "BOOLEAN"),
    ("quality_gate_passed", "BOOLEAN"),
]

KNOWLEDGE_PACKAGES_COLUMNS = [
    ("kttl_profile_id", "VARCHAR(128)"),
]


def _existing_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _add_missing_columns(conn: sqlite3.Connection, table: str, columns: list[tuple[str, str]]) -> list[str]:
    existing = _existing_columns(conn, table)
    added = []
    for name, sql_type in columns:
        if name in existing:
            continue
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}")
        added.append(name)
    return added


def migrate(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        added_coverage = _add_missing_columns(conn, "coverage_results", COVERAGE_RESULTS_COLUMNS)
        added_packages = _add_missing_columns(conn, "knowledge_packages", KNOWLEDGE_PACKAGES_COLUMNS)
        conn.commit()
        print(f"coverage_results: added {added_coverage or '(nothing -- already up to date)'}")
        print(f"knowledge_packages: added {added_packages or '(nothing -- already up to date)'}")
    finally:
        conn.close()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        target = sys.argv[1]
    else:
        import config
        target = str(config.DATABASE_PATH)
    if not Path(target).exists():
        print(f"No database at {target} -- nothing to migrate (a fresh DB already has every column).")
        sys.exit(0)
    migrate(target)
