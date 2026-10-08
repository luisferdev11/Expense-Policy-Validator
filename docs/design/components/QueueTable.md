# QueueTable

The auditor's work list: one row per receipt that needs a person, dense like a spreadsheet and driven like an inbox.

- **Provide:** rows with disposition, receipt ID, merchant, employee and entity, declared type, total in USD, findings (SeverityChips) and age; the selected receipt's ID.
- **Use:** the left side of the split view. `J`/`K` move the selection, `Enter` opens the detail, `X` selects for a bulk action. The open row gets `surface-selected` and a 3px `accent` marker on its first cell.
- **Sorting:** default by severity, then age (oldest first). Saved views ("APAC", "Uncertain items", "Mine") sit above as filter chips.
- **Density:** `row-default` by default; `row-compact` as a setting for heavy users.
- **Do:** right-align the totals in mono with tabular figures; keep the receipt ID a real link.
- **Don't:** put actions in rows. Decisions happen in the detail pane, so the auditor always sees the evidence first.
