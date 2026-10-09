# ADR 0003: Make the architecture visible in the package layout

- **Status:** accepted. It amends the module layout of ADR 0002; the architecture is unchanged.
- **Date:** 2026-10-09
- **Decided by:** Luis, after reviewing the iteration 1 code. The assistant proposed the
  refactor.

## Context

ADR 0002 chose ports and adapters around a pure core. In iteration 1 the code followed that
design only through dependency rules checked by `tests/architecture/test_boundaries.py`. The
folders were organised by component (`classification/`, `engine/`), so the layers could not be
seen in the tree. Luis could not see the architecture when he opened the package.

Reviewing it also found two real leaks of I/O into the core:
- `engine/settings.py` read `docs/decisions/policy_decisions.yaml` and the CSV tables;
- `engine/registry.rules_version()` and `classification/taxonomy.py` read files.

The architecture test banned only network and SDK imports, so it did not catch them.

## Decision

Reorganise the package by layer. Behaviour does not change.

```
src/expense_validator/
  domain/      pure: models, taxonomy table, normaliser, retriever, reporter, engine/ (rules,
               FX, context, uncertainty, disposition, registry, Settings type). No I/O.
  ports/       the two interfaces: classifier.py (ItemClassifier), tracer.py (Tracer)
  adapters/    everything that touches the outside:
               receipts_file.py (loader, labels firewall), config_files.py (settings, rules
               version), results_files.py (read and write outputs), classification_cache.py,
               keyword_classifier.py, openrouter/ (prompt, classifier, prompt sync),
               tracing.py (no-op, guarded, Langfuse)
  app/         composition and use case: pipeline.py, cli.py
  paths.py     repository path constants
```

## Dependency rules

The architecture test enforces each of these:

| Layer | May import | Must not |
|---|---|---|
| `domain` | the standard library's pure modules, pydantic, `domain` itself | `ports`, `adapters`, `app`, `paths`, file and network modules (`os`, `io`, `pathlib`, `csv`, `yaml`, `subprocess`, `socket`, `openai`, `langfuse`, `httpx`, `requests`), or the `open` builtin |
| `ports` | `domain` | `adapters`, `app` |
| `adapters` | `domain`, `ports`, `paths` | `app` |
| `app` | everything | — |

These rules carry over unchanged:
- only `adapters/receipts_file.py` may name the answer keys and the receipts file;
- only the `eval` subcommand of `app/cli.py` may import `eval`.

## Consequences

- **Readable layers.** The tree shows the layers, and every file's layer is its folder.
- **A truly pure core.** The engine receives a `Settings` value built by an adapter, and the
  taxonomy's restricted flags are a static table. A test keeps that table equal to
  `data/category-taxonomy.md`.
- **Proof of no behaviour change.** All 233 tests pass. `outputs/` is regenerated offline and is
  identical except for `run.rules_version`. That field hashes the engine's source files, which
  moved, so it must change.
- **Docs.** `specs/001-mvp-end-to-end/plan.md` and ADR 0002 keep their iteration 1 layout as
  history and point here.
