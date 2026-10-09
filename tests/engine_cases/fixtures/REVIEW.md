# Review of the 13 synthetic engine cases (SC-010, task T092)

- **Reviewer:** Luis.
- **Date:** 2026-10-09.
- **Outcome:** all 13 cases approved as they are. No expected output changed. The one value added
  in conversion (`SYN-03-L1`: `recipient_kind` `government_official`, `recipient_name`
  `Vice-Minister Ortega`) is approved.
- **Status:** every case is now `REVIEWED` in `engine_cases.jsonl`.

The assistant read each case against the policy text and summarised it as below. Luis confirmed
the summary.

| Case | What it tests | Expected | Policy basis |
|---|---|---|---|
| CASE-01 | APAC employee, alcohol at a client dinner with 4 attendees | REG-01 high → flag | REG-01 replaces ALC-01, ALC-02 and ALC-03 for APAC |
| CASE-02 | EMEA employee, an EUR 85 individual meal, no VAT number | REG-03 medium + REG-04 low → flag | EUR 70 at the receipt's own rate (USD 75.60) < USD 91.80; above EUR 50 with VAT absent (A2) |
| CASE-03 | Dinner with a vice-minister, plus a gratuity | GIFT-04 critical on the dinner line only → flag | GIFT-04 covers meals but never the gratuity (EXC-04); A9 |
| CASE-04 | Software subscription with a `PA-` reference | TECH-04 low → review | A `PA-` reference is a pre-approval; TECH-04 needs a manager approval (A5) |
| CASE-05 | Two monitors at USD 160 each, and a USD 249 dock | TECH-02 on the dock only → flag | TECH-02 judges the unit price in USD |
| CASE-06 | Beer on an individual meal, plus a tip | ALC-01 high, citing the beer only → flag | ALC-01; gratuities are never cited |
| CASE-07 | Two meals on the same day, USD 40 and USD 50 | MEAL-01 across receipts → flag | Per person per day across the employee's meal receipts, above $75 domestic |
| CASE-08 | OTC medication of USD 15 and USD 14 on the same trip | HEALTH-01 low on its own lines + MCC-02 → review | A4: the trip total of USD 29 is above $25 |
| CASE-09 | Office supplies at a department store | MCC-02 alone → review | MCC-02 is a signal, never an exception |
| CASE-10 | Wine bought at a supermarket for client entertainment | ALC-03 high + MCC-02 → flag | Retail alcohol is governed by ALC-03 alone |
| CASE-11 | A laptop stand declared as Software | DOC-03 → flag | No line belongs to a category the declared type covers; fees ignored |
| CASE-12 | An item at confidence 0.35 | EXC-03 → review | EXC-03 with the provisional threshold of 0.5; the item leaves every other rule |
| CASE-13 | Laundry on a 2-night trip | LAUNDRY-01 low → review | Fewer than four nights; a single low exception gives review (EXC-01) |
