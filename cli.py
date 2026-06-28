"""
cli.py — Seed-data loader CLI for resetting the demo environment.

Usage:
    python cli.py reset    # drop all tables, recreate schema, reseed
    python cli.py seed     # seed only (idempotent, safe on existing DB)
    python cli.py init     # create schema only, no seed data
"""

import argparse
import logging

from utils.logging_config import configure_logging

configure_logging()
logger = logging.getLogger("kt_assist.cli")


def cmd_init() -> None:
    from database import init_db

    init_db()
    logger.info("Schema initialized.")


def cmd_seed() -> None:
    from database import init_db
    from data.seed_data import seed

    init_db()
    seed()
    logger.info("Seed complete.")


def cmd_reset() -> None:
    import models  # noqa: F401  (register tables on Base.metadata)
    from database import Base, get_engine, init_db
    from data.seed_data import seed

    engine = get_engine()
    logger.info("Dropping all tables...")
    Base.metadata.drop_all(bind=engine)
    init_db()
    seed()
    logger.info("Reset complete: schema recreated and demo data reseeded.")


def main() -> None:
    parser = argparse.ArgumentParser(description="KT Assist environment CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("init", help="Create schema only")
    subparsers.add_parser("seed", help="Seed demo data (idempotent)")
    subparsers.add_parser("reset", help="Drop, recreate, and reseed")

    args = parser.parse_args()
    {"init": cmd_init, "seed": cmd_seed, "reset": cmd_reset}[args.command]()


if __name__ == "__main__":
    main()
