# Langfuse guide: how to inspect the experiments

Langfuse is the lab notebook of this project. The committed files under `explorations/results/`
are the source of truth, and every number in them can be reproduced without Langfuse. Langfuse
is where a person can *look at* every model call: what went in, what came out, what it cost, and
whether it was right.

- **Instance:** self-hosted Langfuse v4. Start it with
  `docker compose -f ~/Documents/percepthor/langfuse/compose.yaml up -d`, then open
  `http://localhost:3020`.
- **Project:** `Expense-Policy-Validator`.
- **Environment:** experiment traces are written to `sdk-experiment`. If a page looks empty,
  select that environment in the top filter.

## What is in there

| Langfuse object | Name | What it holds |
|---|---|---|
| Dataset | `expense-dev-items-draft` | The 109 synthetic line items. Each one has the input (item text, merchant, MCC, language) and the expected output (category, restricted flag). Its metadata records whether Luis reviewed the label or it is still DRAFT |
| Prompt | `classify-item-chat` (label `cls-v1`) | The exact system and user messages sent to the generative models, with the strict JSON schema in its config |
| Prompt | `classify-item-decision` (label `dec-v1`) | The instructions and the 21 category criteria sent to the decision models |
| Experiment | `E13 item classifier` | One run per model (15 runs). Each run has 109 item traces, plus run scores: `accuracy`, `macro_f1`, `restricted_f1`, `usd_per_1000_items` |
| Generation | `classify-item` | One per item and model. It holds the model id, the input messages or decision payload, the output (with the model's reasoning when it returned one), token usage, the cost OpenRouter billed and the linked prompt version. Its metadata keeps the OpenRouter request id, the provider that served it, and the original latency and timestamp |
| Scores | `category_correct`, `restricted_correct`, `confidence` | Per item: did the model match the expected category and the restricted flag, and how confident was it |

## Walkthroughs

**1. Compare models on the same items**
1. Open **Experiments** and select `E13 item classifier`.
2. Tick two or more runs, for example `openai/gpt-oss-120b` and `typesafe/jev-1.13`, and press
   **Compare**.
3. Pick a baseline. The view lines up each item's outputs and scores side by side, with cost and
   latency.
4. Filter on `category_correct = 0` to see only the items a model got wrong.

**2. See one call end to end**
1. From a compare row or from **Tracing**, open an item trace.
2. Expand the `classify-item` generation. It shows the system prompt and user message, or the
   decision payload, the raw answer, tokens, cost and the prompt version.
3. Click the prompt link to open the prompt as it was versioned.

**3. Check what each model cost**
- In **Dashboards** or **Tracing**, group the `classify-item` generations by model.
- The costs are the ones OpenRouter reported for each call, so they match the OpenRouter
  dashboard and `explorations/results/budget_log.jsonl`.

**4. Find the hard items**
- In the dataset view, open an item to see every run's output for it.
- The dataset metadata marks the items whose labels Luis confirmed.

## How to read it honestly

- **These are replays.** The experiment runs were logged from the cached calls, so no model was
  called again and the outputs are exactly the committed ones. Langfuse's latency column
  therefore shows replay time. The real latency is the `original_latency_s` metadata field on
  each generation.
- **Most labels are DRAFT.** Only the items marked as reviewed have been checked by Luis.
  Accuracy here is PRELIMINARY.
- **Only synthetic data goes to Langfuse.** Nothing from `data/receipts.jsonl` is sent.

## Re-logging

```bash
uv run --no-project --with langfuse --with openai --with requests --with python-dotenv \
    python explorations/scripts/langfuse_log_e13.py              # all models
uv run ... python explorations/scripts/langfuse_log_e13.py qwen/qwen3.5-9b   # one model
```

Prompts get a new version only when their text or config changes. Each run of the script adds a
new run per model to the experiment, so delete the old runs first if the cached results have not
changed.
