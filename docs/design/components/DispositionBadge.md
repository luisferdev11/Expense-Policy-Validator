# DispositionBadge

Shows the engine's proposed disposition for a receipt, Flag, Review or Pass, as a pill with its word and icon.

- **Provide:** the disposition (`flag`, `review`, `pass`) and, in the detail header, the one-line reason computed by EXC-01.
- **Use:** first column of every queue row; first element of the detail header, prefixed by "Proposed:" until the auditor decides. After a decision, show the auditor's disposition and keep the proposal in the audit trail.
- **Colors:** Flag uses `high` (every critical, high or medium finding flags), Review uses `low` (only low findings or only signals), Pass uses `pass`. Text takes the matching `on-…` token.
- **Do:** keep the word; it is what screen readers and color-blind users rely on.
- **Don't:** use the badge for severity (that is SeverityChip) or invent a fourth state. "Escalated to Compliance" is a queue, not a disposition.
