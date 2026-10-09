# Archive: the multi-provider model trial (2026-10-07/08)

This is a frozen record, kept as evidence. It is not maintained and does not re-run against the
current `lib/`.

**What it was.** The case's OpenRouter key had expired on the night of 2026-10-07. So the first
model trial ran the same gpt-oss models on Groq and DeepInfra with personal keys, added small
DeepInfra models (Qwen3.5-9B, Gemma 3 12B, Granite 4.2 8B), and added two local ollama models
(qwen3:4b, gemma3:4b). All of them classified the 109 synthetic dev items with prompt `cls-v1`.

**Why it was archived.** The brief gives one model gateway, the OpenRouter key, and that key has
since been renewed. From 2026-10-08 every model call goes through OpenRouter only (Luis's
decision), so the trial was re-run there with a wider model set. See
`explorations/notebooks/05_model_trial.ipynb`.

**What carried over.**
- **The dev set.** The data never changed; its labels are still DRAFT.
- **The OpenRouter gpt-oss runs.** They stayed in `results/trial_runs/` and are reused from the
  cache.
- **The findings.**
  - The dev set does not separate the API models (91.7–99.1 %, with overlapping Wilson
    intervals).
  - The same model on two providers is not identical at temperature 0.
  - The per-item cache is what makes outputs reproducible.

**Contents.**

| Path | What |
|---|---|
| `notebooks/06_local_model_trial.ipynb` and `notebooks/src/` | The executed notebook as it stood at commit `f39e851` |
| `results/` | Predictions and metrics for the nine non-OpenRouter runs |
| `scripts/` | Groq and DeepInfra live check, model listing, smoke check |
| `research/` | The multi-provider shortlist and the live model lists |

**To re-run it,** check out commit `f39e851`, the last commit with multi-provider support in `lib/`.
