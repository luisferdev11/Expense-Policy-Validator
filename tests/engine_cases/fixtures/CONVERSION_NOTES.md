# Conversion notes: synthetic engine cases (DRAFT)

Source: `explorations/dev_set/engine_cases_draft.jsonl` (13 cases, written before decisions
A6 and A9). Task T045 split each receipt into input fields and a per-line classification,
and added `subtype`, `recipient_kind` and `recipient_name`. The default is `none`/`none`/null
for every line; the values below are the only non-default additions. Expected outputs are
unchanged. Luis reviewed and approved all 13 cases on 2026-10-09 (SC-010, task T092):
see REVIEW.md.

Regenerate with:

```bash
uv run python -I tests/engine_cases/fixtures/convert_draft_cases.py \
    explorations/dev_set/engine_cases_draft.jsonl tests/engine_cases/fixtures
```

| Line | Field | Value | Why |
|---|---|---|---|
| SYN-03-L1 | `recipient_kind` | `government_official` | The line text names 'Vice-Minister Ortega (Ministry of Trade)': a government official, so GIFT-04 applies to the meal line (A9). |
| SYN-03-L1 | `recipient_name` | `Vice-Minister Ortega` | The line text names 'Vice-Minister Ortega (Ministry of Trade)': a government official, so GIFT-04 applies to the meal line (A9). |

## Resolutions of failing cases

None yet.
