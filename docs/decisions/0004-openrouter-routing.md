# ADR 0004: Route through OpenRouter and record the serving provider

- **Status:** accepted. It amends the provider pin of research R1 (iteration 2) and the
  reproducibility rule (CLAUDE.md rule 7, constitution v1.2.0).
- **Date:** 2026-10-09
- **Decided by:** Luis, during the E14 runs.

## Context

Every model was pinned to one provider endpoint, `deepinfra/bf16`, with no fallbacks. During
the first E14 runs, DeepInfra answered gemma-3-12b with HTTP 429, "temporarily rate-limited
upstream", on most calls. A pin with no fallback cannot finish a run when its single provider
throttles, and E14 cannot compare a model it cannot run.

## Decision

- Requests name the model only. OpenRouter picks the provider and falls back on failure, among
  providers that honour every request parameter and do not store data
  (`require_parameters: true`, `data_collection: deny`).
- The provider that served each call is recorded: `served_by` on the cache entry, on each
  classification's source, on each dev-run row, and in the Langfuse generation metadata.
- The endpoint label `openrouter` is part of every cache key, so answers from the old pin never
  replay as routed answers.
- E14 re-runs all four models under this routing, so they are compared under the same
  conditions. The DeepInfra runs are kept only as evidence and decide nothing.

## Consequences

- Temperature 0 and the pinned model ID and prompt still hold, but two runs may be served by
  different providers. Replays stay byte-identical, because they read the cached literal answer.
- The committed iteration 1 outputs keep their `deepinfra/bf16` keys until the finalist run
  (T027) regenerates them.
