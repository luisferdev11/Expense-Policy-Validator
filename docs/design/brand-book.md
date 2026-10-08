# Ledgerline: brand book

Ledgerline is the interface language of the Expense Policy Validator: a review tool where software proposes and an auditor decides. Every screen answers three questions in this order: **what is the verdict, why, and what do I do now.**

## Who it is for

| Person | Comes to the product to | Lives in |
|---|---|---|
| **Expense auditor** (shared services, T&E audit) | Clear a queue of receipts the engine flagged or sent to review; confirm or override each with a reason | Review queue and receipt detail, all day, keyboard on |
| **Audit lead / compliance manager** | Watch volume and aging, see where auditors disagree with the engine, sample auto-passed receipts, handle critical findings | Insights, Compliance queue |
| **ML engineer / developer** | Debug a classification, compare prompt and model variants, watch cost and latency | **Not this product: Langfuse** (see "Who sees what") |

Auditors already work in an expense tool's audit console, an email inbox and a spreadsheet. Borrow their habits: an inbox's triage keys, a reading pane next to the list, a spreadsheet's dense sortable columns with right-aligned amounts. Nothing here should need training beyond the shortcut sheet.

## Principles

1. **Verdict first, evidence next, controls last.** The disposition badge and the one-line reason lead every row and every detail pane. Line items, the policy quote and the arithmetic follow. Decision controls sit in a fixed bar at the bottom of the detail pane, always in the same place.
2. **The explanation is the computation.** A finding shows the literal policy sentence it relies on and the steps the engine took, with real numbers (`$187.60 / 4 = $46.90 ≤ $60`). Never paraphrase a rule in a way the policy does not say.
3. **Plain names first, rule IDs second.** Title a finding in the auditor's words ("Alcohol for an APAC employee") and show `REG-01` beside it in `data-strong`. Auditors learn the IDs over time; they never need them to understand the screen.
4. **The engine proposes; the auditor decides.** Copy says "Proposed: Flag", never "Fraud" or "Violation confirmed". An override needs a reason code. Nothing flagged is ever passed without a person.
5. **Show the item's reading, hide the machinery.** The auditor sees what each item was read as (category) and how sure the reading is, as a word: *Certain*, *Likely*, *Uncertain*. Prompts, tokens, latency, provider and model names belong to Langfuse. Version labels ("Policy set 2026.10 · Classifier 3") appear only in the audit trail, because an audit needs them.
6. **Keyboard first, mouse welcome.** `J`/`K` move through the queue, `Enter` opens, `A` confirms the proposal, `O` overrides, `E` escalates to Compliance, `/` searches, `?` shows the sheet. Every shortcut also has a visible button.
7. **Uncertainty is a state, not an error.** An item the classifier is unsure of raises a review signal (EXC-03) and is shown with a dashed outline and the word *Uncertain*, never a warning icon.

## Who sees what: product versus Langfuse

The same events feed both, but each audience sees a different view of them. Do not put developer telemetry in the product, and do not run audits from Langfuse.

| Concept | Auditor and lead see (product) | Developer sees (Langfuse) |
|---|---|---|
| A receipt | Facts, line items, disposition, findings, decision history | One trace with a span per component: normalizer, classifier, retriever, engine, reporter |
| Item category | The category and a confidence word | The prompt version, raw response, numeric confidence, cache hit, model and provider |
| A finding | Plain title, rule ID, severity, cited lines, policy quote, arithmetic | Engine input and output as span attributes (the engine is code; no model call to inspect) |
| Confidence | *Certain / Likely / Uncertain* bands | Calibration: Brier score, reliability diagram, the EXC-03 threshold experiment |
| An override | The auditor's decision and reason code, in the audit trail | A score on the trace ("auditor disagreed: ALC-01"), feeding evaluation datasets |
| Versions | "Policy set 2026.10 · Classifier 3" in the audit trail | Full config: model ID, provider, prompt version, rules commit |
| Cost and speed | Nothing | Tokens, cost per receipt, latency per span |
| Quality | Lead: override rate per rule, flag rate, aging | Dev-set experiments, accuracy with Wilson intervals, McNemar between variants |

The product never links to Langfuse. Support finds a trace from the receipt ID, which is the trace's ID.

## Color

- Set the app on `canvas`; panels and the table on `surface`; policy quotes and computations on `surface-sunken`.
- The top bar is `nav` with `on-nav` text in **both** themes: it anchors the product and matches the deep-navy identity.
- `accent` is for actions, links and the selected-row marker only. It never means a status.
- Status colors follow EXC-01, so color carries the decision rule:
  - `critical`, `high`, `medium` are warm and all mean **Flag**. The Flag badge uses `high`.
  - `low` is cool slate and means **Review**, because only-low becomes review. The Review badge uses `low`.
  - `pass` is teal, never green, so Flag and Pass never read as red against green.
- Every status also carries its word and an icon. Never rely on color alone.
- Solid status fills take their `on-…` token for text. Finding cards take the matching `…-soft` background and the full-strength color for their severity chip.
- Review signals (MCC-02, EXC-03) are not exceptions. Show them as a dashed `low` outline with no fill.

## Type

- `Geist` for interface text, `Geist Mono` for anything that is data: amounts, dates, receipt, line and rule IDs, arithmetic.
- Use `display` once per screen, `title` for a receipt or finding, `heading` for a panel, `body` for everything else.
- Use `label` (sentence case, slight tracking) for field labels and column headers. Never all caps in the table.
- Set every amount column with tabular figures, right-aligned, with its currency code. Show the original amount and the USD conversion together the first time an amount appears: `¥28,000 × 0.0067 = $187.60`.

## Layout

- **App shell:** the `nav` bar, then a split view. The queue sits on the left and the receipt detail takes `detail-pane` (60%) on the right. Opening a receipt never leaves the queue. On screens narrower than 960px the detail replaces the queue, with a back link.
- **Queue rows** are `row-default` (44px), or `row-compact` (36px) in compact density. Columns, in order: disposition, receipt ID, merchant, employee and entity, declared type, total USD (right), findings, age.
- **Detail pane,** top to bottom:
  1. verdict header (badge, plain one-line reason, receipt facts);
  2. findings;
  3. line items, with the cited lines highlighted in the finding's soft color;
  4. rules checked and passed (collapsed);
  5. audit trail;
  6. the fixed decision bar.
- **Spacing** steps from `space-1` to `space-6`: cells use `space-3`, panels `space-4`, and the gap between panels is `space-5`.
- **Radius:** `radius-lg` for panels, `radius-md` for buttons, inputs and cards, `radius-sm` for chips and keys, `radius-pill` only for disposition badges and filter chips.
- **Depth:** `shadow-raised` only on panels over canvas; `shadow-overlay` for menus and dialogs. Rows stay flat.

## Content

- Sentence case everywhere. Second person in instructions ("Choose a reason"), neutral voice in findings ("Alcohol on a receipt from an APAC employee").
- Name the decision, not the button mechanics: "Confirm flag", "Override to review", "Escalate to Compliance".
- Override reasons are codes with a free-text note: *Policy exception approved*, *Wrong category*, *Wrong amount or currency*, *Duplicate of another receipt*, *Other*.
- Dates are ISO with local time and no time zone, as recorded: `2026-05-12 19:30`.
- Empty states say what is done and what is next: "Queue clear. 214 receipts passed automatically today; 10 are waiting for your weekly sample."
- Never write "AI detected", "fraud" or "violation". Write "Proposed: Flag" and let the auditor decide.

## Iconography

- Use Lucide-style line icons (24px grid, 1.75px stroke, round caps), inline SVG in `currentColor`, 16px in rows and 20px in the bar.
- The status icons are fixed:
  - Flag: a flag;
  - Review: an eye;
  - Pass: a check in a circle;
  - Critical: a triangle with an exclamation mark;
  - Uncertain: a dashed circle.
- No emoji, and no illustration inside the product.
- There is no logo yet. Set the product name in `body-strong` on `nav`.

## Focus and accessibility

- Every interactive element shows a 2px solid `focus` ring, offset 2px. The ring holds 3:1 or better on `surface` and `nav` in both themes.
- Text pairs hold 4.5:1 or better in both themes on the grounds their token notes name. Control edges use `border-control`, which holds 3:1.
- Rows are real `<tr>` elements with a link in the receipt ID cell; the decision bar uses real buttons.
