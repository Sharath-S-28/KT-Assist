"""
config/settings.py — Infrastructure settings for KT Assist.

Covers everything that varies by environment or deployment:
filesystem paths, database connection, Claude API credentials,
runtime toggles (DEV_MODE, CACHE_ENABLED), and app-level metadata.

These are the only constants in the config package that read from
environment variables or the filesystem. Every other sub-module
(domain, scoring, templates, ui) is pure Python literals — no I/O,
no env reads — so they can be imported safely in any context.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ── Filesystem paths ─────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent.parent   # repo root (one level up from config/)
DATA_DIR = BASE_DIR / "data"
ASSETS_DIR = BASE_DIR / "assets"
REPORTS_DIR = BASE_DIR / "reports"
PROMPTS_DIR = BASE_DIR / "prompts"

DATABASE_PATH = Path(os.getenv("DATABASE_PATH", DATA_DIR / "kt_assist.db"))
DATABASE_ECHO = os.getenv("DATABASE_ECHO", "false").lower() == "true"

KAI_CACHE_DIR = Path(os.getenv("KAI_CACHE_DIR", DATA_DIR / "cache" / "kai"))
SCENARIO_CACHE_DIR = Path(os.getenv("SCENARIO_CACHE_DIR", DATA_DIR / "cache" / "scenarios"))
GRAPH_STORAGE_DIR = Path(os.getenv("GRAPH_STORAGE_DIR", DATA_DIR / "graphs"))
EXPLANATION_CACHE_DIR = Path(os.getenv("EXPLANATION_CACHE_DIR", DATA_DIR / "cache" / "explanations"))

for _dir in (DATA_DIR, KAI_CACHE_DIR, SCENARIO_CACHE_DIR, GRAPH_STORAGE_DIR, EXPLANATION_CACHE_DIR, REPORTS_DIR):
    _dir.mkdir(parents=True, exist_ok=True)

# ── App / environment ─────────────────────────────────────────────────────────

APP_ENV = os.getenv("APP_ENV", "development")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")

# ── Claude API / cost controls ────────────────────────────────────────────────

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
DEV_MODE = os.getenv("DEV_MODE", "true").lower() == "true"
CACHE_ENABLED = os.getenv("CACHE_ENABLED", "true").lower() == "true"

# Batched semantic boundary checks (KAI cost control) -- objects per Claude call.
SEMANTIC_BATCH_SIZE = 10

# The five logically separated agents (Appendix D), per
# schemas/agent_contracts.py's AgentRequest/AgentResponse envelope.
AGENT_NAMES = ["KAI", "KVA", "KGE", "KRA", "KASE"]
