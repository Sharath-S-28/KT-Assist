"""
scripts/migrate_demo_journey_round_history.py — UI Phase 2 (issue_log
#19) migration for the committed demo DB.

Adds demo_journey_states.closure_round_history_json (nullable TEXT).
Base.metadata.create_all() only creates missing TABLES, never ALTERs
an existing one to add a column -- same reasoning as
scripts/migrate_wave7_hierarchical_columns.py. Safe to run repeatedly
(checks column existence first).

Usage:
    python -m scripts.migrate_demo_journey_round_history
"""

import sqlite3

import database
import models  # noqa: F401 -- register all tables on Base before create_all
from database import Base


def migrate() -> None:
    engine = database.get_engine()
    Base.metadata.create_all(bind=engine)  # ensure demo_journey_states exists on a fresh DB
    db_path = str(engine.url.database)

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(demo_journey_states)")
        existing_columns = {row[1] for row in cur.fetchall()}
        if "closure_round_history_json" in existing_columns:
            print("demo_journey_states.closure_round_history_json already exists -- nothing to do.")
            return
        cur.execute("ALTER TABLE demo_journey_states ADD COLUMN closure_round_history_json TEXT")
        conn.commit()
        print("demo_journey_states: added closure_round_history_json")
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
