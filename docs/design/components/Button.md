# Button

Triggers an action; its label names the decision, not the mechanics.

- **Provide:** a label in sentence case ("Confirm flag"), a variant, and optionally a KeyHint.
- **Variants:** `primary` (`accent`) for the single expected next step on a screen; `secondary` (outline in `border-control`) for alternatives; `ghost` for low-stakes toggles like "Show passed rules"; `critical` only for sending a receipt to Compliance.
- **Size:** `control` height (36px), `radius-md`.
- **Do:** keep one primary per region; show a disabled button with the reason nearby rather than hiding it.
- **Don't:** use `critical` for destructive UI actions in general, or color a button by disposition.
