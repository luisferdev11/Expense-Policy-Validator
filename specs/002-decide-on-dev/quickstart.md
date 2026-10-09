# Quickstart: validating iteration 2

| # | Proves | Steps | Expected |
|---|---|---|---|
| 1 | SC-001 | `build_frozen.py` | It refuses while any item is unreviewed. Once all 130 are reviewed, it writes `dev_set_v2.jsonl` and `FROZEN.md` |
| 2 | SC-002 | `git log` on `experiments_plan.yaml` and on `explorations/results/iter2/` | Every approval commit comes before its experiment's first result commit |
| 3 | SC-004 | `decide.py` with no key | `outputs/eval/experiments.json` comes out byte-identical to the committed file |
| 4 | SC-003 | Search the experiment code for receipts | Only the `eval/` modules read the receipts file |
| 5 | SC-005 | Open `report.md` | Every metric in the experiments table and the oracle section shows its N, and every proportion shows an interval |
| 6 | SC-006 | Open `report.md`, oracle section | Every pipeline error on the 28 receipts has a stage |
| 7 | SC-007 | Spend summary from `decide.py`, and Langfuse | Spend is under USD 1.00. Every billed call has a `classify-item` or `translate-item` generation |
| 8 | US4 | `epv run` with the winners, then `epv eval`, then `epv view` | Results record the chosen model, threshold (`chosen_on_dev`) and config. The viewer has an Experiments view |
| 9 | Regression | `uv run pytest` | All tests pass. The determinism and architecture tests still hold |
