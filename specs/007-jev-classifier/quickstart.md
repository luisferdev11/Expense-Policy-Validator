# Quickstart: jev classifier, shadow mode and E16

Everything below runs from the repository root. Commands marked **billed** call OpenRouter and
need `OPENROUTER_API_KEY` in `.env`. Everything else runs offline with no key.

## 1. Check that nothing changed for the committed configuration

```bash
uv run pytest
uv run pytest tests/integration/test_api_parity.py tests/integration/test_shadow_parity.py
uv run epv run --offline --no-trace          # outputs/results.jsonl must be unchanged
git diff --exit-code outputs/
```

## 2. See the decision adapter and the hybrid work (no key)

```bash
uv run pytest tests/contract/test_decision_classifier.py tests/unit/test_hybrid_merge.py -v
```

## 3. Run the backend with jev in shadow

**Offline (no key).** Every shadow line is `offline_cache_miss`, which proves the plumbing at
zero cost:

```bash
uv run epv serve --with-worker --offline --no-trace --shadow jev-hybrid --db /tmp/epv-shadow.sqlite3
# in another terminal
curl -s -X POST localhost:8000/receipts -H 'content-type: application/json' --data @docs/samples/receipt-one.json
curl -s localhost:8000/receipts/<receipt_id>/shadow | jq
uv run epv shadow report --db /tmp/epv-shadow.sqlite3
```

**Live (billed, cap USD 0.05).** Use the synthetic samples only:

```bash
uv run epv serve --with-worker --shadow jev-hybrid --shadow-cap-usd 0.05 --db /tmp/epv-shadow-live.sqlite3
# submit docs/samples/upload-demo.jsonl through POST /batches, wait for processing, then
uv run epv shadow report --db /tmp/epv-shadow-live.sqlite3
```

The report gives category, restricted, subtype and recipient-kind agreement as k/N with 95 %
Wilson intervals, the disagreement table, agreement with reviewer corrections, and how many
receipts would change disposition. It never reads answer labels. **Do not run shadow on the 32
receipts in `data/` before E16 names a jev variant a finalist** (principle V).

## 4. Experiment E16

1. Read `specs/007-jev-classifier/contracts/e16-rule.md` and the E16 entry in
   `explorations/research/experiments_plan.yaml`.
2. **Luis approved** the rule on 2026-10-12 (`approved_by: Luis` in the entry). Without that line:

   ```bash
   uv run python -I eval/experiments/run_dev.py --experiment E16 --variant jev-hybrid
   # RegistrationError: E16 is registered but not approved by Luis
   ```

3. After approval (**billed**, cap USD 0.10 for the whole experiment):

   ```bash
   uv run python -I eval/experiments/run_dev.py --experiment E16 --variant jev-1.13
   uv run python -I eval/experiments/run_dev.py --experiment E16 --variant jev-hybrid
   uv run python -I eval/experiments/run_dev.py --experiment E16 --variant jev-hybrid --repeat-subset 20
   uv run python -I eval/experiments/decide.py
   ```

4. Read E16 in `outputs/eval/experiments.json`: every variant with its N, the winner, why the
   others lost, the threshold and the dev items it sends to review.

## 5. Migration runbook: only if E16 selects a jev variant

This is not part of this feature. It is a separate decision, made by Luis, in this order:

1. **ADR 0011** (`docs/decisions/0011-item-classifier-jev.md`): cite E16's outcome with its N, the
   shadow report's figures with their N, the cost per 1,000 items, the risks (alpha endpoint,
   non-determinism handled by the cache), and the rollback (restore the pre-migration files from
   git, below).
2. **Alert Luis** that the EXC-03 threshold changes: update `exc03.threshold` and
   `exc03.threshold_status` in `docs/decisions/policy_decisions.yaml` (A3) to E16's
   threshold-step result. This changes `rules_version`.
3. **Switch** `classifier_model: jev-hybrid` (or `jev-1.13`) in `config/pipeline.yaml`.
4. **Regenerate the committed outputs (billed, once):** `uv run epv run`.
   - `epv run` uses the JSONL `ClassificationCache` adapter on `outputs/classifications.jsonl`.
     So this one command appends the jev (and, for the hybrid, gpt-oss) answers for the 78 lines
     to that file, keeping the existing `cls-v2` rows, and writes `outputs/results.jsonl`.
   - **Do not** run `epv cache export` afterwards. It writes the *database* table as JSONL (spec
     006 FR-007), and the table was seeded before the switch, so it would overwrite the file
     with stale content.
   - Existing application databases are not re-seeded (spec 006 FR-006 seeds only an empty
     table). Start the backend on a fresh database, so that it seeds from the new file and bills
     nothing for these lines. Otherwise accept one billed call per line it has not seen.
5. **Report on test once:** `uv run epv eval`. Report the 28 in-scope receipts' metrics with N,
   against the previous classifier's committed metrics, in the README and in the evaluation
   screen data (`npm run evaluation` in `frontend/`).
6. **Re-check offline reproducibility:** `uv run epv run --offline --no-trace` is byte-identical
   to step 4, and `uv run pytest` passes after the parity fixtures are regenerated.
7. **AI_NOTES** and `docs/roadmap.md`, then a PR titled
   `feat: switch the item classifier to jev-hybrid (E16, ADR 0011)`.

**Rollback:** revert the migration PR, or restore the files from the last commit before it:

```bash
git restore --source <pre-migration-commit> -- config/pipeline.yaml docs/decisions/policy_decisions.yaml outputs/
uv run epv run --offline --no-trace && git diff --exit-code outputs/   # byte-identical to that commit
```

Then start the backend on a fresh database, so the table is seeded from the restored file.
Rollback needs no model call.
