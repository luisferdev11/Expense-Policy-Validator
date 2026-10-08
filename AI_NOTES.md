# AI collaboration notes

How coding assistants were used on this project, every mistake they made, how each was caught,
and what changed. Entries are added in the same change as the fix, and are never softened.

## Assistants and what they did

| Assistant | Used for |
|---|---|
| Claude Code (Claude Opus 5.5) | Exploration notebooks, the synthetic dev set draft, provider research, model trials, the decision-model scaffolding, the design system, commits and PRs (as co-author) |

The assistant never sees the answers: `data/receipts.jsonl` is only read through a loader that
strips `labels`, `line_items[].labels` and `notes`, and is never pasted into a prompt or a chat.

## Mistakes log

| # | Date | What went wrong | How it was caught | What changed |
|---|---|---|---|---|
| 1 | 2026-10-07 | The first unattended run was launched headless without access to files outside the repo, and with shell commands it was not allowed to run. It could not read the brief, the strategy or the acceptance checker, and would have worked blind. | Luis read the first minutes of the log and stopped it. | The run was moved into an interactive session. Permissions and a stop gate were checked while Luis was still awake, and the assistant was told to avoid `cd` and compound commands. |
| 2 | 2026-10-07 | The first synthetic dev set had 134 items against a cap of 120. The assistant planned cuts but wrote the full list anyway. | The notebook printed `134 items` on its first build. | 25 plain items (mostly English) were cut, keeping every trap. This happened before any model saw the set, and before its SHA-256 was frozen. |
| 3 | 2026-10-07 | Four synthetic descriptions were near-copies of real receipt lines: three at difflib similarity 1.00, one at 0.90. The assistant had written "typical" examples that already exist in the data. | The contamination check asserted similarity < 0.85 and failed. The probe printed only synthetic IDs and scores, never the real text. | Those four items and five more above 0.70 were rewritten. The worst similarity is now 0.69. |
| 4 | 2026-10-07 | Notebook commentary contained hand-typed numbers, including "PPV ≈ 0.93" at the dataset's prevalence. The computed value is 0.918. | Self-review before execution, against the rule that no number is typed by hand. | Every number in the commentary is now printed by code next to the computation. |
| 5 | 2026-10-07 | The paired minimum-detectable-difference search crashed (`StopIteration`). At 10 % discordance no difference can exceed the discordance, so no answer exists. | The notebook failed during execution. | The search returns `None` ("not detectable") and the notebook shows several discordance rates. |
| 6 | 2026-10-07 | Some of the assistant's own explanations shared exact 6-word sequences with the hidden answer notes. A reviewer would read that as leakage, even though nothing was read. | The acceptance checker's leakage test flagged 4 fragments by file. | The fragments were not looked up, since that would mean reading the answers. Engine-case explanations and rule triggers were rewritten as pseudo-code, and the checker was re-run as a black box. |
| 7 | 2026-10-08 | The model trial's headline was "Qwen3.5-9B is best (99.1 %)", but the comparison does not support it. All API models sit between 91.7 % and 99.1 % with overlapping Wilson intervals, on labels the same assistant wrote. | Wilson intervals and the minimum detectable difference at N = 109 (about 0.12), computed in the same notebook. | Results are marked PRELIMINARY. Hardening the dev set, with labels reviewed by Luis, is now the first item of `experiments_plan.yaml`. |
| 8 | 2026-10-08 | The classifier code only supported chat models returning JSON, so it left no room for decision models (jev, OpenAI Decisions, open-weight decision encoders). | Luis asked whether the code was ready for them. | Added one `ItemClassifier` interface, with endpoints that are refused until each schema is verified, a price is recorded and a key exists. Added the experiments plan E1–E12. |
| 9 | 2026-10-08 | A regex-based re-indentation of `run_trial.py` produced misaligned code. | The assistant read the edited lines back. | The block was fixed by hand and checked with ruff and a no-network dry run. |
| 10 | 2026-10-08 | The OpenRouter key check appended the full `/key` response to a committed log, including the key's masked label and account identifiers. | Self-review of the output before committing. | The script now keeps only limit, usage and expiry, and the logged row was filtered before the commit. |
| 11 | 2026-10-08 | The assistant treated OpenRouter's `GET /api/v1/generation?id=` as failing because it returned 404 for every call within about 40 seconds, and the key's `usage` still read 0. Both records actually lag the call by many minutes. | Re-checking about half an hour later: 4 of 6 ids verified, all served by DeepInfra, each billed exactly the `usage.cost` the response had reported. Key usage had started moving. | The live check no longer concludes anything from an immediate 404. `openrouter_verify.py` can be re-run later, and it checks the provider and the billed cost against the cost the response reported. The OpenRouter cap uses the larger of reported and measured spend. |

## Open issues

- Two of the six OpenRouter live-check ids were still 404 at the last check. Re-run
  `explorations/openrouter_verify.py` later; it overwrites `openrouter_verification.jsonl`.

## Checked by hand (pending)

- The DRAFT dev-set labels, starting with the eight marked *debatable*.
- The 13 engine edge cases and the 8 policy ambiguities.
