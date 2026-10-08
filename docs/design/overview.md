# Product design: overview

The viewer this project ships is a small Streamlit app, but it is designed as the first slice of
the review tool an audit team would use. This folder holds the design system it follows. The full
mockups live as shared design artifacts:

- **Design system "Ledgerline"** (tokens, components, previews, brand book):
  https://claude.ai/artifact/DYC5UFwcUcZExPkAJD8kPs
- **Mockup canvas**: https://claude.ai/artifact/EMAPwShVsAojUGiPCHtzqZ
  - auditor workbench in light and dark;
  - a compliance case (GIFT-04);
  - audit-lead insights;
  - "who sees what";
  - three system-design options:
    - A: a batch pipeline plus a viewer;
    - B: serverless and asynchronous on AWS;
    - C: containers with a self-hosted model.

Every example in the mockups uses the synthetic engine cases (`SYN-*`), never the real receipts.

## Files

| File | What it is |
|---|---|
| `brand-book.md` | Personas, usability principles, colour, type, layout, voice, and the product-versus-Langfuse split |
| `components/*.md` | Usage guidelines for the eight components: DispositionBadge, SeverityChip, ConfidenceBand, FindingCard, QueueTable, DecisionBar, Button, KeyHint |
| `tokens.json` | Design tokens with light and dark values |
| `ledgerline.css` | CSS for the components, to reuse in the Streamlit viewer |

## Product decisions

1. **The engine proposes; the auditor decides.** Dispositions read "Proposed: Flag". Overriding
   a proposal needs a reason code, and nothing flagged is ever passed without a person.
2. **Status colours encode EXC-01, with no red/green pair.**
   - Critical, high and medium findings use warm tones and lead to flag.
   - Low findings use slate and lead to review.
   - Pass uses teal.
3. **The explanation is the computation.** Every finding shows the literal policy sentence and
   the arithmetic with real numbers, as EXC-04 asks.
4. **No machinery in the auditor's view.** The auditor never sees the model, provider, prompt,
   tokens, cost or latency. Classifier confidence appears only as *Certain*, *Likely* or
   *Uncertain*, and an EXC-03 item is shown as *Uncertain*, not as an error.
5. **Version labels only in the audit trail.** The policy-set and classifier versions are recorded
   with every decision, because an audit has to be reproducible.
6. **Developers work in Langfuse, not in the product.**
   - Dev-set model comparisons live in Langfuse.
   - The receipt ID is the trace ID.
   - Auditor overrides flow back to Langfuse as an `auditor_agreement` score, which is the
     production signal for the classifier.
