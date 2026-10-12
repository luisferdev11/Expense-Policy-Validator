# Front end (iteration 4)

React, Vite and TypeScript on the HTTP API of iteration 3, with the Ledgerline design
(`docs/design/`). It decides nothing: every verdict comes from the API's deterministic engine.

## Run it

```bash
# 1. the API, on a throwaway database (no keys, no model calls)
uv run epv serve --with-worker --offline --no-trace --db /tmp/epv-front.sqlite3 --cache /tmp/epv-front-cache.jsonl

# 2. the app (http://localhost:5173); EPV_API points at the API, default http://localhost:8000
cd frontend && npm install && EPV_API=http://localhost:8000 npm run dev
```

The browser calls a same-origin `/api` prefix that Vite proxies, because the API sends no CORS
headers (`FINDINGS.md` F-04).

## Screens

| Route | What it is |
|---|---|
| `/queue`, `/compliance`, `/sample`, `/all` | Split view: list on the left, receipt on the right; `?batch=<id>` narrows to one batch; deciding opens the next receipt |
| `/intake` | Submit one receipt or a batch; per-row outcome; batch progress; retry of failed receipts |
| `/history/:id` | Events, what each revision changed, evaluation versions |
| `/how-it-works` | The states, who acts in each, and the events |
| `/insights` | Volume, aging, agreement with the engine, rules that fire, each with its N |
| `/evaluation` | Scores against baselines, confusion matrices, per-rule results, five classifiers on the dev set (including jev-1.13), confidence, decisions and base rate, from `public/evaluation.json` |

A receipt shows the verdict, the findings with the literal policy text, the line items with how
each was read, revisions, the audit trail and a fixed decision bar. Actions follow
`allowed_actions`; overriding the engine asks for a reason; a stale decision (HTTP 409) is
explained and the receipt is refreshed.

## Checks

```bash
npm test          # unit tests of the helpers and a check of the API contract against docs/api/openapi.json (Vitest)
npm run typecheck
npx playwright install chromium   # once
npm run e2e       # smoke tests per screen (Playwright), against its own throwaway backend
```

`npm run e2e` starts the API on port 8777 with a fresh SQLite file and the app on 5177. Set
`EPV_SHOTS=<dir>` to save screenshots.

## Evaluation data

```bash
npm run evaluation   # rebuilds public/evaluation.json from outputs/eval and data/; no model call
# the jev-1.13 dev-set run (calls OpenRouter; key from .env, traced in Langfuse; about USD 0.006)
uv run python -I frontend/scripts/jev_dev_run.py
```

A test fails when `public/evaluation.json` is stale, and checks that it holds no receipt ID or answer key.

## Notes

- Money stays a string end to end; nothing is converted to a float.
- Shortcuts: `J`/`K` move, `A` approve, `R` reject, `I` request information, `E` escalate,
  `C` correct a category, `/` search, `?` the sheet.
- The author name in the bar is recorded as the actor of each action (there is no
  authentication in this iteration).
- Gaps and proposals for the backend are in `FINDINGS.md`.
