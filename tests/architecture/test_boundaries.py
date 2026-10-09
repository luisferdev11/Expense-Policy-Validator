"""Layer boundaries of the architecture (ADR 0002, ADR 0003, FR-002, constitution I and II).

Layers: domain (pure), ports, adapters, app. The scan covers `src/expense_validator/` and
`viewer/`. Two explicit exceptions carry over from iteration 1:
- `adapters/receipts_file.py` may name the answer keys and the receipts file, because it strips
  them (analysis I1);
- `app/cli.py` may import `eval` lazily inside its eval subcommand function (analysis I2).
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "src" / "expense_validator"
SCANNED = [*PACKAGE.rglob("*.py"), *(ROOT / "viewer").rglob("*.py")]
DOMAIN = sorted((PACKAGE / "domain").rglob("*.py"))
PORTS = sorted((PACKAGE / "ports").rglob("*.py"))
ADAPTERS = sorted((PACKAGE / "adapters").rglob("*.py"))
LOADER = PACKAGE / "adapters" / "receipts_file.py"
CLI = PACKAGE / "app" / "cli.py"
EVAL_SUBCOMMAND = "_cmd_eval"

DOMAIN_BANNED = (
    "expense_validator.ports",
    "expense_validator.adapters",
    "expense_validator.app",
    "expense_validator.paths",
    "os",
    "io",
    "pathlib",
    "csv",
    "yaml",
    "subprocess",
    "socket",
    "shutil",
    "openai",
    "langfuse",
    "httpx",
    "requests",
    "streamlit",
)
PORTS_BANNED = ("expense_validator.adapters", "expense_validator.app")
ADAPTERS_BANNED = ("expense_validator.app",)


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


def _violations(files: list[Path], banned: tuple[str, ...]) -> list[str]:
    return [
        f"{path.relative_to(ROOT)} imports {name}"
        for path in files
        for _, name in _imports(_parse(path))
        if any(name == b or name.startswith(b + ".") for b in banned)
    ]


def test_every_layer_exists_and_the_scan_finds_it() -> None:
    assert DOMAIN and PORTS and ADAPTERS
    assert LOADER in SCANNED and CLI in SCANNED


def test_domain_imports_no_outer_layer_and_no_io_or_network_module() -> None:
    assert _violations(DOMAIN, DOMAIN_BANNED) == []


def test_domain_never_calls_open() -> None:
    offenders = [
        str(path.relative_to(ROOT))
        for path in DOMAIN
        for node in ast.walk(_parse(path))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open"
    ]
    assert offenders == []


def test_ports_import_only_the_domain() -> None:
    assert _violations(PORTS, PORTS_BANNED) == []


def test_adapters_never_import_the_app_layer() -> None:
    assert _violations(ADAPTERS, ADAPTERS_BANNED) == []


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
