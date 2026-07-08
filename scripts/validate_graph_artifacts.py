"""
scripts/validate_graph_artifacts.py — consistency validator for
KnowledgeGraphVersion DB rows vs. the actual graph JSON artifact files
on this machine (issue_log #22).

Purpose: detect, BEFORE a live demo or a fresh-checkout API call, the
exact class of problem this issue was filed for -- a committed/copied
database whose KnowledgeGraphVersion rows reference graph artifacts
that were never committed (data/graphs/ is gitignored by design; only
the bootstrap source code is committed) and therefore don't exist on
this machine. Read-only by default; never mutates data unless
--repair is passed, and even then only relocates rows whose artifact
can be verified to exist (delegates to
scripts.migrate_graph_storage_paths' already-tested repair logic --
no duplicate repair logic here).

Per-row classification:
  - valid:       storage_path already resolves as the portable form.
  - relocatable: doesn't resolve as stored, but the artifact exists at
                 the deterministic (package_id, version_number)
                 location -- --repair will fix these.
  - missing:     no artifact found anywhere for this row. This is the
                 exact "fresh checkout, never bootstrapped" case --
                 the fix is to run the demo bootstrap
                 (scripts.reset_hierarchical_demo +
                 scripts.run_hierarchical_demo_replay_proof), not to
                 repair a path, since there is nothing to point at.

Also reports orphaned files: graph JSON files present on disk with no
corresponding KnowledgeGraphVersion row (harmless, but useful to know
about).

Usage:
    python -m scripts.validate_graph_artifacts [--repair] [--package-id ID]
"""

import argparse
from pathlib import Path

import config
import database
import models  # noqa: F401 -- register all tables on Base before create_all
from database import Base
from models import KnowledgeGraphVersion
from services.graph.graph_storage import _portable_storage_path, _resolve_graph_path


def validate(package_id: str | None = None) -> dict:
    engine = database.get_engine()
    Base.metadata.create_all(bind=engine)
    session = database.get_session_factory()()

    query = session.query(KnowledgeGraphVersion)
    if package_id:
        query = query.filter_by(package_id=package_id)
    rows = query.order_by(KnowledgeGraphVersion.package_id, KnowledgeGraphVersion.version_number).all()

    report = {"valid": [], "relocatable": [], "missing": [], "orphaned_files": []}

    referenced_files: set[Path] = set()
    for row in rows:
        portable = _portable_storage_path(row.package_id, row.version_number)
        try:
            resolved = _resolve_graph_path(row.storage_path, row.package_id, row.version_number)
        except Exception:
            report["missing"].append({
                "package_id": row.package_id, "version_number": row.version_number,
                "stored_storage_path": row.storage_path, "expected_portable_path": portable,
            })
            continue

        referenced_files.add(resolved.resolve())
        entry = {
            "package_id": row.package_id, "version_number": row.version_number,
            "stored_storage_path": row.storage_path, "expected_portable_path": portable,
            "resolved_at": str(resolved),
        }
        if row.storage_path == portable:
            report["valid"].append(entry)
        else:
            report["relocatable"].append(entry)

    # Orphaned files: anything under GRAPH_STORAGE_DIR not referenced by
    # any row we just resolved (scoped to package_id if one was given).
    if config.GRAPH_STORAGE_DIR.is_dir():
        search_root = (
            config.GRAPH_STORAGE_DIR / package_id if package_id else config.GRAPH_STORAGE_DIR
        )
        if search_root.is_dir():
            for path in search_root.rglob("v*.json"):
                if path.resolve() not in referenced_files:
                    report["orphaned_files"].append(str(path))

    return report


def _print_report(report: dict) -> None:
    print(f"valid:            {len(report['valid'])}")
    print(f"relocatable:      {len(report['relocatable'])}")
    print(f"missing:          {len(report['missing'])}")
    print(f"orphaned_files:   {len(report['orphaned_files'])}")

    if report["missing"]:
        print("\nMISSING (no artifact found anywhere -- run the demo bootstrap, do not hand-repair):")
        for entry in report["missing"]:
            print(f"  package={entry['package_id']} version={entry['version_number']} "
                  f"stored={entry['stored_storage_path']!r}")

    if report["relocatable"]:
        print("\nRELOCATABLE (artifact exists, path just needs updating -- rerun with --repair):")
        for entry in report["relocatable"]:
            print(f"  package={entry['package_id']} version={entry['version_number']} "
                  f"stored={entry['stored_storage_path']!r} -> {entry['expected_portable_path']!r}")

    if report["orphaned_files"]:
        print(f"\nORPHANED FILES (on disk, no DB row references them -- informational only, "
              f"showing first 10 of {len(report['orphaned_files'])}):")
        for path in report["orphaned_files"][:10]:
            print(f"  {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repair", action="store_true",
                         help="Repair relocatable rows in place (delegates to migrate_graph_storage_paths).")
    parser.add_argument("--package-id", default=None, help="Scope the check to one package.")
    args = parser.parse_args()

    report = validate(package_id=args.package_id)
    _print_report(report)

    if args.repair:
        if report["relocatable"]:
            print("\nRunning repair (scripts.migrate_graph_storage_paths)...")
            from scripts.migrate_graph_storage_paths import migrate
            counts = migrate(dry_run=False)
            print(f"repaired: {counts['repaired']}")
        else:
            print("\nNothing to repair.")

    if report["missing"]:
        print(
            "\nSome rows reference graph artifacts that do not exist anywhere on this machine. "
            "This is expected on a fresh checkout -- data/graphs/ is intentionally not committed "
            "to git (same as the KAI cache). Run the demo bootstrap to regenerate them:\n"
            "    python -m scripts.reset_hierarchical_demo\n"
            "    python -m scripts.run_hierarchical_demo_replay_proof"
        )


if __name__ == "__main__":
    main()
