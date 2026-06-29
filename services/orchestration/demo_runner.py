"""
services/orchestration/demo_runner.py — deprecated location, re-export shim.

DemoRunner moved to services/demo/demo_runner.py to match the Phase 12
build spec's file table (the spec text was not available in this repo
when this module was first built here under services/orchestration/,
alongside workflow_runner.py). The sandbox this was built in could not
unlink the old file (PermissionError on the shared mount), so it is
kept as a thin re-export instead of a duplicate implementation, to
avoid two divergent copies of the same logic.
"""

from services.demo.demo_runner import DemoLog, DemoRunner, DemoStep, SceneResult

__all__ = ["DemoLog", "DemoRunner", "DemoStep", "SceneResult"]
