# Contract: experiment commands

Every command runs from the repository root. None of them reads `data/receipts.jsonl`, except
`eval/oracle.py`, which runs through `epv eval`.

| Command | Does | Model calls |
|---|---|---|
| `uv run python -I explorations/dev_set/build_frozen.py` | Merges the reviews into `dev_set_v2.jsonl`, writes `FROZEN.md` with the SHA-256, and refuses to run while any item is unreviewed | None |
| `uv run python -I eval/experiments/run_dev.py --experiment E14 --variant <pin>` | Classifies the frozen set with one pin. Cached and traced, and it checks that the set's hash matches the registration | Yes, under the cap |
| `uv run python -I eval/experiments/run_dev.py --experiment E5 --variant translate` | Translates, then classifies, the non-English items with the reference pin | Yes |
| `uv run python -I eval/experiments/run_dev.py ... --offline` | Replays a run from its cache | None |
| `uv run python -I eval/experiments/retriever_check.py` | Compares the trigger map with all rules on fixtures and receipts | None |
| `uv run python -I eval/experiments/decide.py` | Applies every registered rule to the committed results and writes `outputs/eval/experiments.json` | None |
| `uv run epv eval` | Also writes the oracle ablation and the experiments table | None |

**Guarantees:**
- `run_dev.py` refuses an experiment that has no approved registration, or whose `data` hash
  differs from the frozen set's.
- `decide.py` is deterministic: the bootstrap seed is fixed.
