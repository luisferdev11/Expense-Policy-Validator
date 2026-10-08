# FindingCard

Presents one exception the engine raised, with everything an auditor needs to agree or disagree without opening the policy.

- **Provide:** a plain-language title, the rule ID and severity, the policy document, the cited line IDs (never a gratuity or service fee), the literal policy sentence, and the engine's steps with real numbers. All of it comes from the engine's output; the UI writes nothing of its own.
- **Use:** in the receipt detail, one card per exception, most severe first. The card's soft background (`critical-soft`, `high-soft`, `medium-soft`, `low-soft`) matches its chip, and the cited rows in the line-items table take the same soft color.
- **Steps:** say where precedence applied ("REG-01 replaces ALC-01…") and, when an override decides the outcome, what the global rule alone would have said. That is the question auditors ask.
- **Do:** quote the policy exactly, in `body` on `surface`, with the file and rule under it.
- **Don't:** paraphrase the rule in the quote, show a model's prose as the explanation, or hide the arithmetic behind a toggle.
