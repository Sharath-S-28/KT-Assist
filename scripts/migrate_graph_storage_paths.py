"""
scripts/migrate_graph_storage_paths.py — repairs legacy, environment-
specific absolute KnowledgeGraphVersion.storage_path values into the
portable, repository-relative form (issue_log #21).

Scans every KnowledgeGraphVersion row and, for each one:
  - if storage_path is already the portable relative form and resolves
    to an existing file: reports "already_valid", makes no change.
  - if storage_path is a legacy absolute path (any OS, any prior
    machine/temp directory) but the equivalent graph file can be
    deterministically located at
    config.GRAPH_STORAGE_DIR/{package_id}/v{version_number}.json in
    THIS environment: verifies the file exists, then rewrites
    storage_path to the portable relative form. Reports "repaired".
  - if no equivalent file can be found anywhere: reports "unresolved"
    and leaves the row completely untouched -- never points a row at a
    nonexistent file, never fabricates one.

Idempotent: safe to run repeatedly; a second run reports everything as
"already_valid" (nothing left to repair).

Usage:
    python -m scripts.migrate_graph_storage_paths [--dry-run]
"""

import argparse

import config
import database
import models  # noqa: F401 -- register all tables on Base before create_all
from database import Base
from models import KnowledgeGraphVersion
from services.graph.graph_storage import _portable_storage_path, _resolve_graph_path


def migrate(dry_run: bool = False) -> dict[str, int]:
    engine = database.get_engine()
    Base.metadata.create_all(bind=engine)
    session = database.get_session_factory()()

    counts = {"already_valid": 0, "repaired": 0, "unresolved": 0}
    rows = session.query(KnowledgeGraphVersion).order_by(
        KnowledgeGraphVersion.package_id, KnowledgeGraphVersion.version_number
    ).all()

    for row in rows:
        expected_portable = _portable_storage_path(row.package_id, row.version_number)
        if row.storage_path == expected_portable:
            try:
                _resolve_graph_path(row.storage_path, row.package_id, row.version_number)
                counts["already_valid"] += 1
                continue
            except Exception:
                pass  # falls through to the repair attempt below

        try:
            _resolve_graph_path(row.storage_path, row.package_id, row.version_number)
        except Exception:
            counts["unresolved"] += 1
            print(f"UNRESOLVED  package={row.package_id} version={row.version_number} "
                  f"stored_path={row.storage_path!r} -- no equivalent graph file found locally.")
            continue

        if row.storage_path != expected_portable:
            print(f"REPAIRED    package={row.package_id} version={row.version_number}: "
                  f"{row.storage_path!r} -> {expected_portable!r}")
            if not dry_run:
                row.storage_path = expected_portable
            counts["repaired"] += 1
        else:
            counts["already_valid"] += 1

    if not dry_run:
        session.commit()
    else:
        session.rollback()

    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Report only, do not write changes.")
    args = parser.parse_args()

    counts = migrate(dry_run=args.dry_run)
    print()
    print(f"already_valid: {counts['already_valid']}")
    print(f"repaired:      {counts['repaired']}")
    print(f"unresolved:    {counts['unresolved']}")
    if args.dry_run:
        print("(dry run -- no changes written)")
    if counts["unresolved"]:
        print(
            "\nRows reported UNRESOLVED were left untouched. Their graph artifact does not exist "
            "anywhere findable in this environment -- the underlying package/version genuinely "
            "needs to be reseeded or re-ingested; do not manually point it at an unrelated file."
        )


if __name__ == "__main__":
    main()
