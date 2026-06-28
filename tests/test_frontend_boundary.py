"""
tests/test_frontend_boundary.py — Phase 11's locked architectural rule,
mechanically enforced: every Streamlit module under frontend/ (and the
future streamlit_app.py entry point at repo root) may reach the backend
only through frontend/api_client.py over HTTP. No module in that surface
may import services, agents, models (the ORM package), storage, or
database directly -- doing so would silently couple the frontend to
Python internals and falsify the "a React rewrite only touches
api_client" migration claim (Appendix A's locked decision).

schemas/ is the one explicit exception (Pydantic response shapes only,
no behavior, no DB session) -- api_client.py itself imports schemas/ to
parse HTTP responses into typed objects without redefining every field
name a second time.

This is an AST walk over each file's import statements, not a runtime
import-hook -- the same "prove it mechanically" discipline as Phase 9's
number guard and Phase 10's aggregate-don't-re-score test.
"""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

FORBIDDEN_TOP_LEVEL_MODULES = {"services", "agents", "models", "storage", "database"}


def _frontend_surface_files() -> list[Path]:
    """Every .py file under frontend/, plus streamlit_app.py at the repo
    root if/when it exists (Session 33's entry point)."""
    files = [
        p
        for p in (REPO_ROOT / "frontend").rglob("*.py")
        if "__pycache__" not in p.parts
    ]
    entry_point = REPO_ROOT / "streamlit_app.py"
    if entry_point.exists():
        files.append(entry_point)
    return files


def _imported_top_level_modules(file_path: Path) -> set[str]:
    """Every distinct top-level module name a file imports, via either
    `import x.y` or `from x.y import z` (relative imports -- `from . import
    x` -- have no module name at this level and are skipped; this codebase
    doesn't use them)."""
    tree = ast.parse(file_path.read_text(), filename=str(file_path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                modules.add(node.module.split(".")[0])
    return modules


def test_frontend_surface_is_nonempty():
    """Sanity check the guard is actually looking at files -- an empty
    glob would make every other assertion in this file vacuously true."""
    assert len(_frontend_surface_files()) >= 2  # __init__.py, api_client.py, theme.py today


def test_no_frontend_module_imports_backend_internals():
    violations: dict[str, set[str]] = {}
    for file_path in _frontend_surface_files():
        imported = _imported_top_level_modules(file_path)
        forbidden_hits = imported & FORBIDDEN_TOP_LEVEL_MODULES
        if forbidden_hits:
            violations[str(file_path.relative_to(REPO_ROOT))] = forbidden_hits

    assert not violations, (
        "frontend/ modules must reach the backend only through "
        f"frontend/api_client.py over HTTP; found direct imports of backend "
        f"internals: {violations}"
    )


def test_api_client_only_imports_schemas_from_backend():
    """api_client.py is the one place allowed to cross into the backend's
    own code at all -- and even there, only schemas/ (Pydantic response
    shapes), never services/agents/models/storage/database."""
    api_client = REPO_ROOT / "frontend" / "api_client.py"
    imported = _imported_top_level_modules(api_client)
    assert not (imported & FORBIDDEN_TOP_LEVEL_MODULES)
    assert "schemas" in imported
