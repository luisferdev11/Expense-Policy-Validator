"""Static boundaries of the architecture (T010, FR-002, constitution I and II, ADR 0002).

The scan covers `src/expense_validator/` and `viewer/` only. Two explicit exceptions:
- `loader.py` may name the answer keys and the receipts file, because it strips them (I1);
- `cli.py` may import `eval` lazily inside its eval subcommand function (I2).
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "src" / "expense_validator"
SCANNED = [*PACKAGE.rglob("*.py"), *(ROOT / "viewer").rglob("*.py")]
PURE_CORE = [
    PACKAGE / "models.py",
    PACKAGE / "normaliser.py",
    PACKAGE / "retriever.py",
    PACKAGE / "reporter.py",
    *(PACKAGE / "engine").rglob("*.py"),
]
NETWORK_OR_ADAPTER = (
    "openai",
    "langfuse",
    "httpx",
    "requests",
    "expense_validator.classification.openrouter",
    "expense_validator.tracing",
)
LOADER = PACKAGE / "loader.py"
CLI = PACKAGE / "cli.py"
EVAL_SUBCOMMAND = "_cmd_eval"


def _imports(tree: ast.AST) -> Iterator[tuple[ast.AST, str]]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node, alias.name
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            yield node, node.module


def _docstrings(tree: ast.AST) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                ids.add(id(body[0].value))
    return ids


def _strings(tree: ast.AST) -> Iterator[str]:
    skip = _docstrings(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip:
            yield node.value


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _enclosing_functions(tree: ast.Module) -> dict[int, str]:
    owner: dict[int, str] = {}
    for fn in ast.walk(tree):
        if isinstance(fn, ast.FunctionDef):
            for node in ast.walk(fn):
                owner.setdefault(id(node), fn.name)
    return owner


def test_scan_finds_the_package() -> None:
    assert LOADER in SCANNED


def test_pure_core_imports_no_network_sdk_or_adapter() -> None:
    offenders = [
        f"{path.relative_to(ROOT)} imports {name}"
        for path in PURE_CORE
        if path.exists()
        for _, name in _imports(_parse(path))
        if any(name == banned or name.startswith(banned + ".") for banned in NETWORK_OR_ADAPTER)
    ]
    assert offenders == []


def test_only_the_cli_eval_subcommand_imports_eval() -> None:
    offenders = []
    for path in SCANNED:
        tree = _parse(path)
        owner = _enclosing_functions(tree)
        for node, name in _imports(tree):
            if name == "eval" or name.startswith("eval."):
                allowed = path == CLI and owner.get(id(node)) == EVAL_SUBCOMMAND
                if not allowed:
                    offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


def test_only_the_loader_names_the_receipts_file() -> None:
    offenders = [
        str(path.relative_to(ROOT))
        for path in SCANNED
        if path != LOADER and any("receipts.jsonl" in s for s in _strings(_parse(path)))
    ]
    assert offenders == []


def test_only_the_loader_names_the_answer_keys() -> None:
    offenders = [
        str(path.relative_to(ROOT))
        for path in SCANNED
        if path != LOADER and any(s in {"labels", "notes"} for s in _strings(_parse(path)))
    ]
    assert offenders == []
