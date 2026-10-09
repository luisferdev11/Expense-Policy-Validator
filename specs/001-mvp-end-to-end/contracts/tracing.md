# Contract: trace shape in Langfuse

This implements CLAUDE.md rule 11 and constitution principle X for iteration 1. The `Tracer` port
has two implementations: `LangfuseTracer` and `NoopTracer` (research R6).

## Pipeline run (`epv run`)

| Observation | Type | Parent | Records |
|---|---|---|---|
| `validate-receipt` | trace root span | — | Input: the receipt with answer fields already stripped. Output: the `ReceiptResult`. Metadata: `rules_version`, `prompt_version`, `classifier`. The trace ID is `create_trace_id(seed=f"{run_label}:{receipt_id}")` |
| `normalise-receipt` | span | root | Cleaned items |
| `classify-receipt` | span | root | Per item: `cache_hit` and `cache_key`. On a hit, the original `request_id` |
| `classify-item` | generation | `classify-receipt` | One per **billed model call** only. It records: the model and endpoint; the exact messages (system and user); the response content and the reasoning; usage (prompt and completion tokens); the billed cost from `usage.cost`; the linked Langfuse prompt `classify-item-chat` (`cls-v2`); the OpenRouter request id; latency |
| `decide-receipt` | second top-level span, same trace ID | — | Output: the `ReceiptResult`. It exists because deciding needs every receipt classified first: the cross-receipt context is built between the two passes (ADR 0002, flow step 4) |
| `retrieve-rules` | span | `decide-receipt` | The selected rule IDs |
| `apply-rules` | span | `decide-receipt` | The findings |
| `report-exceptions` | span | `decide-receipt` | The final explanations |

**Two passes per run.** Each receipt's trace therefore has two top-level spans:
`validate-receipt` (normalise, classify) and `decide-receipt` (retrieve, apply, report). Both use
the trace ID derived from the same seed. The run label is unique per run and is recorded in the
gitignored `.cache/runs.json` (one entry per results file), so `epv eval` can score the latest run's traces.

**Names.** Every name is stable and verb-first. No name contains a model name.

**Labels firewall.** No answer field, `notes` value or correct answer appears in any pipeline
observation.

## Evaluation (`epv eval`)

- Scores are attached to the same trace IDs, derived from the same seed:
  - `disposition_correct` (0 or 1);
  - `category_correct_rate`;
  - `exceptions_matched`;
  - `exceptions_extra`.
- Scores are written only when Langfuse is reachable. Otherwise the evaluation skips them with
  a warning.

## Failure behaviour

- **No keys, or `auth_check()` fails or times out:** `NoopTracer`, with one warning.
- **Any tracer exception mid-run:** switch to `NoopTracer`, with one warning. The run continues.
- **The final flush** runs in a daemon thread joined with a timeout. On timeout, a warning, exit
  code unchanged.
- **Outputs never depend on the tracer.** The determinism test runs with `NoopTracer` and with
  a fake recording tracer, and compares the bytes.
