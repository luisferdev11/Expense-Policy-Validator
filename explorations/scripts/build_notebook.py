"""Build and execute one exploration notebook from its py:percent source.

Usage, from the repository root:

    uv run --no-project --with jupyter --with jupytext --with pyyaml --with pandas \
        --with numpy --with scipy --with matplotlib --with openai --with python-dotenv \
        --with requests python explorations/scripts/build_notebook.py 01_rule_inventory

It converts explorations/notebooks/src/<name>.py into explorations/notebooks/<name>.ipynb, puts the
re-run command in the first cell, and executes the notebook in place with nbconvert.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import jupytext
import nbformat

EXP = Path(__file__).resolve().parent.parent  # explorations/
DEPS = [
    "jupyter",
    "pyyaml",
    "pandas",
    "numpy",
    "scipy",
    "matplotlib",
    "openai",
    "python-dotenv",
    "requests",
]


def rerun_command(name: str) -> str:
    withs = " ".join(f"--with {d}" for d in DEPS)
    # Runs from any directory inside the repository: it resolves the root with git first.
    return (
        f'(cd "$(git rev-parse --show-toplevel)" && uv run --no-project {withs} '
        f"jupyter nbconvert --to notebook --execute --inplace explorations/notebooks/{name}.ipynb)"
    )


def main(name: str) -> None:
    src = EXP / "notebooks" / "src" / f"{name}.py"
    nb = jupytext.read(src)
    header = nbformat.v4.new_markdown_cell(
        "Re-run this notebook from anywhere inside the repository with:\n\n"
        f"```bash\n{rerun_command(name)}\n```"
    )
    nb.cells.insert(0, header)
    nb.metadata["kernelspec"] = {
        "name": "python3",
        "display_name": "Python 3",
        "language": "python",
    }
    out = EXP / "notebooks" / f"{name}.ipynb"
    nbformat.write(nb, out)
    cmd = [
        sys.executable,
        "-m",
        "jupyter",
        "nbconvert",
        "--to",
        "notebook",
        "--execute",
        "--inplace",
        "--ExecutePreprocessor.timeout=3600",
        str(out),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    print(result.stdout[-3000:])
    print(result.stderr[-3000:])
    if result.returncode != 0:
        sys.exit(result.returncode)
    print(f"built and executed {out.name}")


if __name__ == "__main__":
    main(sys.argv[1])
