# ConfidenceBand

Shows how sure the classifier is about one item's category, as one of three words with a small three-step meter.

- **Provide:** the band (`certain`, `likely`, `uncertain`), computed by the product from the classifier's score and the EXC-03 threshold; the thresholds live in configuration, not in the UI.
- **Use:** in the line-items table next to each category. Uncertain items raise the EXC-03 review signal and are left out of every rule, so the band says "sent to review".
- **Do:** keep the word visible; the meter is decoration (`aria-hidden`).
- **Don't:** show the numeric probability, calibration charts or model names here: those belong to Langfuse. An auditor cannot act on 0.82 versus 0.86.
