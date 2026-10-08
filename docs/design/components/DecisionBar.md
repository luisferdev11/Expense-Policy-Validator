# DecisionBar

Captures the auditor's decision on the open receipt: confirm the proposal, override it with a reason, or escalate it.

- **Provide:** the proposed disposition (it names the primary button, "Confirm flag" or "Confirm review"), the allowed overrides, and the reason codes.
- **Use:** fixed to the bottom of the detail pane, always in the same place. `A` confirms, `O` opens the override row, `E` escalates to Compliance. After saving, the queue moves to the next receipt.
- **Override:** needs a target disposition and a reason code; the note is required only for "Other". Never offer "Pass" without the reason row.
- **Critical findings:** the primary button becomes "Send to Compliance" (`critical` fill); the auditor cannot pass the receipt from here.
- **Do:** log every decision with the auditor, time, policy-set and classifier version labels; the proposal is never overwritten.
- **Don't:** add a free "Approve all" button; bulk actions exist only for the weekly sample of auto-passed receipts.
