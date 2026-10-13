"""Repository paths used by the pipeline. Pure constants, no I/O."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
POLICY_DIR = DATA_DIR / "policy-docs"
TAXONOMY_FILE = DATA_DIR / "category-taxonomy.md"
DECISIONS_FILE = REPO_ROOT / "docs" / "decisions" / "policy_decisions.yaml"
CONFIG_DIR = REPO_ROOT / "config"
OUTPUTS_DIR = REPO_ROOT / "outputs"
RESULTS_FILE = OUTPUTS_DIR / "results.jsonl"
CLASSIFICATIONS_FILE = OUTPUTS_DIR / "classifications.jsonl"
BASELINES_DIR = OUTPUTS_DIR / "baselines"
EVAL_DIR = OUTPUTS_DIR / "eval"
DEV_OUTPUTS_DIR = OUTPUTS_DIR / "dev"
RAW_CACHE_DIR = REPO_ROOT / ".cache" / "raw"
VAR_DIR = REPO_ROOT / "var"
DEFAULT_DB_FILE = VAR_DIR / "epv.sqlite3"
# Iterations 3 and 4 kept the backend's answers here. The backend now stores them in the
# `classification_cache` table of its database (spec 006); nothing writes this file.
APP_CLASSIFICATION_CACHE = REPO_ROOT / ".cache" / "app_classifications.jsonl"
