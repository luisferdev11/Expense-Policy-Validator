# Quickstart: validating iteration 1

Each scenario proves one spec criterion. Commands are in `contracts/cli.md`; shapes are in
`data-model.md` and `contracts/receipt-result.md`.

## Prerequisites

- uv with Python 3.12, then `uv sync`.
- Optional:
  - `.env` with `OPENROUTER_API_KEY` (see `.env.example`). Only needed for a cold cache.
  - Langfuse keys, with Langfuse running locally (`docs/ai/langfuse-guide.md`). Only needed for
    traces.

## Scenarios

| # | Proves | Steps | Expected |
|---|---|---|---|
| 1 | SC-002, US2 | `uv run pytest` with no `.env` and no network | All pass: the five brief cases, the 13 DRAFT engine cases, determinism, the firewall, architecture, verbatim evidence, the retriever superset, classifier contracts |
| 2 | SC-001, US1 | `uv run epv run --offline` on the committed cache | 32 results in `outputs/results.jsonl`. `git diff --exit-code outputs/` is clean |
| 3 | SC-003 | Run scenario 2 twice | Byte-identical. The stderr summary shows 0 model calls and USD 0.00 |
| 4 | SC-006 | `uv run epv run --offline` after moving `outputs/classifications.jsonl` aside (restore it afterwards) | Every receipt is `review` or `flag`, none `pass`. Each line has an EXC-03 signal with `offline_cache_miss` |
| 5 | SC-007 | `uv run epv run --offline` with Langfuse stopped | One tracer warning. The output is identical to scenario 2 |
| 6 | SC-007 | `uv run epv run` with Langfuse up and a cold cache for one item | One `classify-item` generation with model, messages, output, reasoning, usage, cost, prompt link and request id (`contracts/tracing.md`) |
| 7 | SC-004, US3 | `uv run epv eval` with no key | `outputs/eval/` is reproduced byte for byte. Every metric shows its N. The 28 receipts are scored and 4 are listed as not scored |
| 8 | US3 | Open `outputs/eval/report.md` | Every FR-030 and FR-031 item, three systems (pipeline, `keyword-classifier`, `keyword-flagger`), two failure-case slots, the base-rate table at 1 %, 3 % and 5 % |
| 9 | SC-009, US4 | `uv run epv view` with no network | Three views. A mismatch is visually distinct. A receipt's detail shows the evidence, the explanation and the answer from `comparison.jsonl` |
| 10 | SC-008 | Stderr summary of the cold run, against the OpenRouter dashboard | Iteration spend is under USD 1.00, and the reported and dashboard figures roughly agree |
| 11 | SC-010 | `explorations/dev_set/engine_cases_draft.jsonl` review record | Luis has reviewed all 13 cases. Changes are recorded with their reasons |

## MVP done

All eleven scenarios pass on a clean checkout, and the roadmap's iteration 1 exit criteria hold.
