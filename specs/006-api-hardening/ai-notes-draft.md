# AI notes draft: spec 006 implementation

Rows for `AI_NOTES.md`, written by the implementation session of 2026-10-12 and folded in by the
parent session (this file is deleted once folded in). Columns: what happened | how it was caught |
what changed.

| What happened | How it was caught | What changed |
|---|---|---|
| T003 said "`uv add --dev locust`" and record the resolved version, but `uv add` resolved Locust 2.46.7, uploaded 2026-10-04: eight days old, under the project's two-week rule for new dependencies. | Reading the upload time in `uv.lock` before committing. | Pinned `locust==2.46.6` (2026-09-17); the plan's Technical Context records both. |
| T003 also said to add `perf` to `[tool.mypy] files` in the setup phase, but `perf/` does not exist until Phase 7 and mypy would fail on a missing path. | Reasoning about the order before the first commit. | The entry is added in T064, with the package. |
| The phase 1 commit chain piped ruff, mypy and pytest through `tail -1`, so a failing pytest (the stale `docs/api/openapi.json` after the version bump) and a failing `ruff format --check` (two spec markdown files with unformatted Python snippets, which ruff 0.16 checks) did not stop the commit. | Reading the summary lines printed right after the commit. | Amended the unpushed commit: regenerated the OpenAPI document and formatted the two markdown snippets. Checks now run without `tail`, so a non-zero exit stops the chain. |
