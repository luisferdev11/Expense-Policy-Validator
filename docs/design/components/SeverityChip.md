# SeverityChip

Names one finding by its rule ID and severity, so a row tells the auditor what fired and how serious it is.

- **Provide:** the rule ID and its severity (`critical`, `high`, `medium`, `low`), or `signal` for a review signal.
- **Use:** in the queue's Findings column, one chip per finding, highest severity first; in a FindingCard's header.
- **Colors:** solid `critical`, `high`, `medium`, `low` fills with their `on-…` text. Review signals (MCC-02, EXC-03) use the dashed `low` outline with no fill, because they are context, never exceptions.
- **Do:** set the rule ID in mono and the severity word in sans, so the chip reads "REG-01 high".
- **Don't:** show more than three chips in a row; collapse the rest into "+2".
