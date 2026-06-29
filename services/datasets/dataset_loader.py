"""
services/datasets/dataset_loader.py — Phase 13 dataset loading.

[PROPOSAL ruling -- ground-truth file location]: the spec's §8 sketch
puts fixtures under data/<dataset>/ground_truth/. The real, already-
built config.py instead reserves data/ entirely for gitignored runtime
state (data/*.db, data/cache/, data/graphs/ — see config.py's DATA_DIR
block and .gitignore). Putting version-controlled dataset fixtures
inside a directory whose contents are explicitly never committed would
be a real bug, not a style choice. Dataset fixtures instead live in a
new top-level `datasets/<name>/{assets,ground_truth}/` tree, parallel
to `data/` rather than inside it.

A dataset directory's `assets/` holds exactly one source document (the
content KAI ingests, kept human-readable for the runbook/demo
narrative); `ground_truth/` holds the machine-readable files this
module loads: extraction_mock.json (the exact payload fed to
WorkflowRunner.ingest), expected_objects.json (initial/final
GroundTruthGraph), intentional_gaps.json, and gap_answers.json.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DATASETS_ROOT = Path(__file__).resolve().parent.parent.parent / "datasets"


class DatasetNotFoundError(Exception):
    pass


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise DatasetNotFoundError(f"Missing ground-truth file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _single_asset_path(assets_dir: Path) -> Path:
    candidates = sorted(p for p in assets_dir.iterdir() if p.is_file())
    if not candidates:
        raise DatasetNotFoundError(f"No asset file found in {assets_dir}")
    return candidates[0]


def load_dataset(name: str) -> dict[str, Any]:
    """Load one dataset's asset content + every ground-truth file.

    Returns a dict with: name, asset_filename, asset_content (bytes),
    extraction_mock, expected_objects, intentional_gaps, gap_answers.
    Raises DatasetNotFoundError if the dataset directory or any
    required ground-truth file is missing -- never silently returns a
    partial/empty dataset.
    """
    root = DATASETS_ROOT / name
    if not root.exists():
        raise DatasetNotFoundError(f"No dataset directory at {root}")

    assets_dir = root / "assets"
    ground_truth_dir = root / "ground_truth"
    asset_path = _single_asset_path(assets_dir)

    return {
        "name": name,
        "asset_filename": asset_path.name,
        "asset_content": asset_path.read_bytes(),
        "extraction_mock": _read_json(ground_truth_dir / "extraction_mock.json"),
        "expected_objects": _read_json(ground_truth_dir / "expected_objects.json"),
        "intentional_gaps": _read_json(ground_truth_dir / "intentional_gaps.json"),
        "gap_answers": _read_json(ground_truth_dir / "gap_answers.json"),
    }


def list_datasets() -> list[str]:
    if not DATASETS_ROOT.exists():
        return []
    return sorted(p.name for p in DATASETS_ROOT.iterdir() if p.is_dir() and (p / "ground_truth").exists())
