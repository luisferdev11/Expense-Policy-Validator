# Research: jev classifier, shadow mode and E16

Each entry gives the decision, why, and what was rejected. The sources are files in this
repository, read on 2026-10-12.

## R1. Shadow, not a traffic split

- **Decision:** gpt-oss-120b keeps deciding every receipt. The jev-based classifier runs as a
  shadow, and its answers are stored and compared. Adoption goes only through E16.
- **Why:** principle V (decide on dev). A split would let an unregistered model decide real
  receipts. Shadow data on real traffic is still valuable: model-to-model agreement, agreement with
  reviewer corrections, and the disposition impact. None of it needs labels.
- **Rejected:** a per-receipt hash split (an unvalidated model would decide); offline only (Luis
  asked to see jev beside the current model in the backend).

## R2. Shadow as its own outbox stage

- **Decision:** completing `classify` queues a `shadow` item next to `evaluate`. The shadow item
  is processed independently and never touches receipt state.
- **Why:** running the shadow inline in `_classify` (`app/worker.py:125-182`) would add jev's and
  gpt-oss's latency to every receipt before evaluation. It would also mix shadow failures with
  `ClassificationUnavailableError`, which fails the stage. A separate stage reuses the leased
  outbox (claims, retries, crash resume) at no new cost.
- **Rejected:** an inline call (delays receipts, couples failures); a separate process with its own
  queue (more moving parts for no gain at this scale).

## R3. The switch lives in `classifier_model`, the shadow outside `pipeline.yaml`

- **Decision:** the primary classifier is chosen by the existing `classifier_model` key. Shadow
  mode is a worker flag or environment variable.
- **Why:** `RunMetadata.pipeline_config_version` is a hash of `config/pipeline.yaml`
  (`adapters/config_files.py:75-84`), and it is written into every result. Adding a shadow key
  there would change `outputs/results.jsonl` and break the byte-for-byte parity test, although
  the shadow decides nothing. Switching the primary classifier *should* change that hash, because
  it is a decision.
- **Rejected:** a new `classifier:` key replacing `classifier_model` (it would rename a committed
  key and change the hash for nothing).

## R4. Hybrid merge rules

- **Decision:** the category and confidence come from jev; the subtype, recipient kind and
  recipient name come from gpt-oss-120b, with the merge table of `contracts/decision-adapter.md`.
- **Why:**
  - jev's category beat gpt-oss's on dev (130/130 against 123/130), and its top probability is
    better calibrated (Brier 0.0109 against 0.0365).
  - The prompt `cls-v2` forbids a subtype unless the category is `other`, and `Classification`
    enforces that (`domain/models.py`, A6).
  - So gpt-oss's subtype is only usable when both models say `other`. Otherwise the subtype is
    `none`, and the conflict is traced rather than resolved by a third call.
  - The recipient fields describe the line text, not the category, so they are taken as they are.
- **Rejected:**
  - Asking jev for subtype and recipient as extra decision questions. That would be a new prompt
    (`dec-v2`) with no dev evidence, so it is a candidate for a later experiment.
  - Calling gpt-oss only when jev says `other`. The recipient matters for every category (GIFT-01,
    GIFT-03, GIFT-04).

## R5. Which confidence feeds EXC-03 for jev

- **Decision:** the top probability (`probabilities[choice]`) by default, falling back to the
  reported `confidence`. E16 chooses between them with E7's procedure, and re-chooses the
  threshold.
- **Why:** on 2026-10-11 both were measured with N = 130: top probability Brier 0.0109 and ECE
  0.0503; reported confidence Brier 0.0120 and ECE 0.0523 (`frontend/data/classifier-comparison.json`).
  The current threshold, 0.97 (A3, ADR 0005), was chosen on gpt-oss's self-reported confidence and
  cannot be reused.
- **Note:** if every dev answer is correct, E7's procedure picks a threshold of 0, because no
  candidate sends fewer correct items to review. That is a valid, reported outcome, not a bug.
  It also shows the limit of N = 130 (FINDINGS F-03 proposes a dev set of 500 or more).

## R6. Where the shadow report's statistics live

- **Decision:**
  - Move `wilson` from `eval/stats.py` into a new pure module, `src/expense_validator/domain/stats.py`.
  - `eval/stats.py` re-exports it (`from expense_validator.domain.stats import wilson`), so every
    existing caller and test keeps working.
  - The comparison and the report counts live in `domain/shadow.py`. The report command lives in
    `app/shadow_report.py` and `app/cli.py`.
- **Why:**
  - The architecture test lets only the CLI's eval subcommand import `eval`
    (`tests/architecture/test_boundaries.py:124`, `test_only_the_cli_eval_subcommand_imports_eval`).
  - `eval/` may import the package, but the package may not import `eval/`.
  - Moving the function keeps a single implementation of the interval.
- **Rejected:**
  - A second copy of `wilson`: the two copies could drift apart.
  - Relaxing the architecture test.

## R7. Moving the decision payload into the package

- **Decision:** `DECISION_INSTRUCTIONS` and `decision_payload` move from
  `explorations/lib/decision_adapters.py` to `adapters/openrouter/decision_prompt.py`. A fixture
  (`tests/fixtures/dec_v1_payload.json`), captured once from the exploration code, pins the
  payload for 3 synthetic items.
- **Why:** package code must not import `explorations/` (it is research code, put on `sys.path`
  by hand). The fixture proves that the moved payload is the one E13 and the 2026-10-11 run used,
  so the dev evidence stays valid.

## R8. Reproducibility of a non-deterministic model

- **Decision:** cache every literal response (spec 006 port) before parsing. Replays read the
  cache. E16 measures repeatability once (20 items, a second uncached call).
- **Why:** E8 and E11 showed that output is not byte-stable even at temperature 0, and jev is
  documented as varying between calls (`explorations/research/05_technical_spike.md`). The cache is
  what makes `epv run --offline` byte-identical (principle VII).

## R9. The two gaps in `decide.py`

- **Superiority before the guard** (`eval/experiments/decide.py:137-146`). A challenger with
  p < 0.05 and a positive lower bound becomes `superior` before the A6/A9 guard is checked.
  jev-1.13's 2026-10-11 rows are labelled `superior` (in `classifier-comparison.json`) although
  they are 23/29 wrong on A6/A9.
- **The reference always qualifies** (line 104, `qualifying = [REFERENCE]`, and line 153, cheapest
  wins). A superior challenger that costs more than the reference loses to it, which contradicts
  the registered text ("becomes the reference").
- **Fix:** guards first, then superiority, and a superior challenger wins outright. A test shows
  that E14's committed outcome is unchanged (no E14 challenger was superior).
- **What the 2026-10-11 numbers would have said under the fixed rule:** jev-1.13 →
  `fails_a6a9_guard`, so the reference is kept. Under the buggy rule: jev-1.13 superior and
  cheaper, so jev wins, although it cannot feed six rules.

## R10. Verification without spending on the scored receipts

- **Decision:**
  - Tests use fake transports.
  - The live smoke check runs shadow on the two synthetic samples in `docs/samples/`, with a cap
    of USD 0.05.
  - A jev variant runs on the 32 receipts only once, after E16 names it a finalist, and is then
    reported with its N.
- **Why:** principle V: the 28 in-scope receipts run once per finalist. The committed cache holds
  only gpt-oss answers for those 78 lines, so an offline shadow run on them would only record
  `offline_cache_miss`. That proves the plumbing, but it measures nothing.
