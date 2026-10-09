# Cross-Artifact Analysis: Iteration 1 MVP

**Run**: `/speckit-analyze`, 2026-10-08, after `/speckit-tasks`.
**Artifacts checked**: `spec.md`, `plan.md`, `research.md`, `data-model.md`, `contracts/`,
`tasks.md`, the constitution v1.1.0, `docs/roadmap.md` and ADRs 0001–0002.
**Method**:
- Mechanical scans: language, placeholders, FR/SC references in tasks, deferred-item keywords,
  and answer-field mentions.
- A manual mapping of every requirement to its tasks.

The analysis was read-only. Luis approved the fixes, and they were applied in the commit that
adds this file.

## Findings and resolutions

| ID | Category | Severity | Finding | Resolution |
|---|---|---|---|---|
| C1 | Constitution (X) | CRITICAL | The thin-path cold run (T039) would bill model calls before prompt `cls-v2` existed in Langfuse; it was pushed only in T076. Those generations would lack the linked prompt that principle X requires | T028 adds `prompt_sync.py`, called before the first billed call of every run. T039 checks the push and the link first. `contracts/cli.md` states it |
| I1 | Inconsistency | HIGH | The architecture test (T010, R7) banned the literals `"labels"` and `"notes"` outside `eval/`. `loader.py` must name them to strip them, so the test would fail on correct code | `loader.py` is exempt. The scan covers `src/expense_validator/` and `viewer/` only (T010, R7) |
| I2 | Inconsistency | HIGH | "Nothing outside `eval/` imports `eval`" contradicted `epv eval`, which `cli.py` must dispatch | One allowed exception: a lazy import inside the `eval` subcommand of `cli.py`. The test checks that it stays there (T010, T038, R7) |
| U1 | Underspecification | MEDIUM | T039 used an `--only` filter that `contracts/cli.md` did not define | `--only RECEIPT_ID ...` is added to the CLI contract as a development option. It writes to gitignored `outputs/dev/`, never to `outputs/results.jsonl` (T004, T038) |
| G1 | Coverage gap | MEDIUM | No task tested FR-027 (no answers in traces) | T070's recording tracer asserts that no answer-only key (`labels`, `notes`, `expected_exceptions`) and no answer-only text (`notes`, answer `reason` strings) appears in any captured payload |
| I3 | Inconsistency | MEDIUM | Spec US1, scenario 1, said every line has a taxonomy category. FR-009 and the data model allow `category: null` for an unclassified line | The scenario now names the exception: unclassified, with a reason and EXC-03 |
| G2 | Coverage gap | MEDIUM | The tests did not cover A4's "raise HEALTH-01 on every receipt of the trip with OTC lines" | T054 adds the case, plus the exact $25.00 boundary |
| L1 | Traceability | LOW | Only 9 of 45 FR/SC IDs were cited in tasks | 55 tasks now carry their FR/SC references. Every FR and SC is referenced by at least one task |

## Extra checks requested by Luis

- **English only.** Pass. The 19 changed artifacts contain no Spanish text and no accented
  characters.
- **No task implements a deferred item.** Pass.
  - Mentions of a queue, auth, API, E5/E7/E14, ablation, README or AWS appear only in the
    "Out of scope" list.
  - Pushing the prompt to Langfuse (T028, T076) and posting eval scores (T085) belong to
    CLAUDE.md rule 11, not to L7.
- **Labels firewall in tasks.** Pass, after I1.
  - The brief-case tests and the contamination guard read receipts only through the loader.
  - The viewer takes answers from `outputs/eval/comparison.jsonl`.
  - The 13 synthetic engine cases are not answers from `receipts.jsonl`.

## Metrics

| Metric | Before fixes | After fixes |
|---|---|---|
| Requirements (FR + SC) | 45 | 45 |
| Tasks | 97 | 97 |
| Requirements with at least one task | 45, with FR-027 only partly covered | 45 |
| Critical issues | 1 | 0 |
| High issues | 2 | 0 |
| Ambiguities | 0 | 0 |
| Duplications | 0 | 0 |
