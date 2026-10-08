# ADR 0001: How the engine resolves the policy ambiguities

- **Status:** accepted, with two questions left open for the review session (see the end)
- **Date:** 2026-10-08
- **Decided by:** Luis. The assistant (Claude Code) proposed the options and a recommendation for
  each.
- **Input:** `explorations/policy_ambiguities.yaml`, eight places where the policy text admits more
  than one reading. Each has a verbatim quote.
- **Machine-readable copy:** `docs/decisions/policy_decisions.yaml`. The spec and the engine read
  that file, and every rule implementation cites the decision it follows.

## Summary

| ID | Rules | Decision | Configurable |
|---|---|---|---|
| A1 | REG-03, REG-04, REG-05, DOC-04 | Currency conversion goes through one FX policy with explicit settings. By default it uses the rate recorded on the receipt, as of the transaction date. When the euro rate is needed but not on the record, it comes from a versioned rate table, and a missing rate sends the receipt to review | Yes. The date basis and the rate kind are a switch; see Q1 |
| A2 | REG-04 | VAT number is an optional input field. Absent means missing, as the policy says. Applied to EMEA-entity employees above EUR 50 | The field mapping, when production data carries it; see Q2 |
| A3 | EXC-03 | Confidence threshold chosen on the synthetic dev set before touching the 28 receipts; how often it fires and what it costs are reported; a higher production threshold is argued separately | Yes, a single named threshold |
| A4 | HEALTH-01 | When a trip's OTC total exceeds $25, raise on every receipt of that trip with OTC lines, each citing its own medication lines | No |
| A5 | EXC-02, TECH-02, ENT-01, TECH-04, PERS-01, PERS-02 | The kind of an approval reference is inferred from its prefix through a table. `PA-` is a pre-approval and satisfies only TECH-02 | Yes, the prefix table |
| A6 | ENT-01, TECH-03, HEALTH-01 (prescription) | For category `other`, the classifier also returns a closed subtype: `event_ticket`, `mobile_handset`, `prescription_medication` or `none`. The engine reads only that field, never free text | The subtype list is versioned with the prompt |
| A7 | GIFT-01 | Literal definition. An item is a gift only if the receipt is declared Client Gifts or the line names a recipient. A gift-category item outside that is not tested under GIFT-01; DOC-03 catches the mismatch | No |
| A8 | MEAL-01 | The home currency comes from a full ISO 4217 country→currency table, so domestic vs international never needs a guess | The table is data, versioned |

## Decisions in detail

### A1. Currency conversion and the euro rate (REG-03, REG-04, REG-05, DOC-04)

**Ambiguity.** REG-03 and REG-04 compare against EUR thresholds "at the euro rate on the
transaction date". For a receipt in another currency, that rate is not on the record. The brief
says "Convert foreign currency first, using the rate on the receipt."

**Luis's note** (translated from Spanish):

> Be clear about where we switch between converting with the purchase date or with the billing
> date, because a currency can move a lot and it depends on the business. We can ask the
> evaluators in the session and just flip the switch. I am not sure whether there is an API that
> converts by date. We also need to document the business rule for which rate to use from that
> day: the highest, the lowest or the mid rate. This is one of the important open questions.

**Decision.**
- All conversion goes through one FX component with two explicit settings.
  - `date_basis`: `transaction` (default) or `billing`. The data only has the transaction date. REG-05 says "the rate on the transaction date, which must be recorded on the expense record".
  - `rate_kind`: `recorded` (default) or `mid`, `high`, `low` from a rate source.
- **Default, which matches the policy text and the brief:** the rate recorded on the receipt, as of the transaction date.
- **When the euro rate is needed but not recorded:**
  - It comes from a versioned table in the repo that records its source and fetch date.
  - A candidate source is ECB reference rates, which are daily mid rates. This is not yet verified for this project.
  - If the date is missing from the table, the receipt goes to **review**, never to pass.
- **In this dataset** every EMEA receipt is in EUR, so the default never needs the table. The switch matters for production.

**Why.** The default keeps the scored behaviour exactly as the policy states. Making the basis a
setting turns a business question into a configuration change, not a code change.

### A2. VAT number (REG-04)

**Ambiguity.** "Where the expense record does not capture a VAT number, treat it as missing." No
receipt in the dataset records a VAT number, so read literally, every EMEA receipt above EUR 50
raises a low exception.

**Luis's point.** The field can exist in production even though this dataset lacks it. This is a
real data problem and must stay on record.

**Decision.**
- The input model gets an optional `vat_number` field.
- REG-04 applies to receipts of **EMEA-entity** employees above EUR 50, converted per A1. The rule sits under the EMEA entity heading.
- When `vat_number` is absent, it is missing, and REG-04 raises a low exception as the policy says.
- The evaluation reports how many REG-04 exceptions come only from the missing field. This keeps the effect of the data gap visible instead of silently inflating review volume.

### A3. Uncertainty threshold (EXC-03)

**Ambiguity.** The policy gives no confidence threshold, and the answers never use EXC-03, so
every signal costs a point in the evaluation.

**Decision.**
- Choose the threshold on the synthetic dev set, from the coverage-accuracy curve and calibration (Brier score and ECE), before any run on the 28 receipts.
- Report how many times it fired on the 28 and what it changed.
- Argue for a higher threshold in production. The policy itself says "a missed review costs far less than a false accusation".

**Note.** Self-reported confidence is not byte-stable across calls (experiment E11). The
threshold is applied to the cached response, so a re-run makes the same decision.

### A4. OTC medication across a trip (HEALTH-01)

**Decision.**
- Once the OTC total over all receipts of a trip exceeds $25, raise HEALTH-01 as a low exception on **every** receipt of that trip that has OTC lines.
- Each exception cites that receipt's own medication lines.
- This matches how MEAL-01 marks every receipt that contributes to a breached day, and it does not depend on the order of the receipts.

### A5. Kind of approval reference (EXC-02)

**Decision.**
- A prefix table maps each reference to its kind. `PA-` is a pre-approval and satisfies only TECH-02.
- No prefix in the data maps to a VP approval (ENT-01), a manager approval (TECH-04) or a baggage-delay reference (PERS-01, PERS-02), so those carve-outs never apply here.
- The table is configuration, ready for production prefixes.

### A6. Items the taxonomy sends to `other` (ENT-01, TECH-03, prescription medication)

**Decision.**
- When the category is `other`, the classifier also returns a closed `subtype`: `event_ticket`, `mobile_handset`, `prescription_medication` or `none`.
- The engine reads only this structured field. No keyword matching happens inside the engine, so it stays deterministic and auditable.
- The subtype list is part of the versioned prompt and schema.

### A7. What counts as a gift (GIFT-01)

**Decision.**
- Follow the literal definition: "An item is a gift when the receipt is declared as Client Gifts or the line names who it is for."
- A gift-category item on another receipt type, with no named recipient, is not tested under GIFT-01. DOC-03 still flags that the contents do not match the declared type.

### A8. Home currency for domestic vs international (MEAL-01)

**Decision.**
- Use a full ISO 4217 country→currency table, versioned as data with its source.
- Travel is international when the receipt currency differs from the home currency of the employee's country. On a day that mixes both, the higher cap applies.

## Open questions for the review session

These are business decisions, so they go to the panel rather than being guessed. The code is
built so that each answer only flips a setting.

- **Q1. FX date basis and rate kind.**
  - Should foreign amounts convert at the transaction date or the billing date?
  - Should the rate be the one recorded on the expense, or a reference mid, high or low rate?
  - Which rate source is authoritative, and is there an approved API?
- **Q2. VAT data in production.** Will the expense record carry a VAT number field? If yes, in
  what format, and should its validity be checked or only its presence?
