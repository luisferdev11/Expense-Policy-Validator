"""The two failure cases of the evaluation (brief, Part 3): receipts the system got wrong.

Each one names the run in which it happened, the stage that caused it (translation,
classification, retrieval or rule logic), what happened and what would change. The final run has
no disposition error on the 28 scored receipts, so both cases are from earlier runs of the same
system. They are reviewed text, not computed: the evidence column points to the committed
decision records, and the receipt IDs live in eval/ because pipeline code never names one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Stage = Literal["translation", "classification", "retrieval", "rule_logic"]
STAGES: tuple[Stage, ...] = ("translation", "classification", "retrieval", "rule_logic")


@dataclass(frozen=True)
class FailureCase:
    receipt_id: str
    run: str
    stage: Stage
    cause: str
    what_happened: str
    change: str
    evidence: str


FAILURE_CASES: tuple[FailureCase, ...] = (
    FailureCase(
        receipt_id="RCP-007",
        run="iteration 1 (v0.1.1, gpt-oss-120b pinned to deepinfra/bf16)",
        stage="classification",
        cause="the model's answer broke the output schema",
        what_happened=(
            "The line 'Assorted soft drinks' came back as JSON with `\"subtype\": null`. The "
            "cls-v2 parser is strict, so the line was `unclassified` (schema_violation). EXC-03 "
            "turned the missing category into a review signal, the receipt went to review, and "
            "that was the run's only disposition error. Reading null as `none` would have given "
            "the right disposition. Experiment E15 then tested exactly that on the dev set and "
            "found no net fix (2 null subtypes in 520 answers), so the parser stayed strict; the "
            "final run classifies the line correctly, but one malformed answer still turns a "
            "line into a review signal."
        ),
        change=(
            "Retry a schema violation once before giving up on the line, and re-run E15 on a "
            "larger dev set. A strict parser is right; a single malformed answer should not "
            "decide a receipt."
        ),
        evidence="AI_NOTES 33, docs/decisions/0005-iteration-2-decisions.md (E15)",
    ),
    FailureCase(
        receipt_id="RCP-012",
        run="iteration 2, first pass of the finalist (gpt-oss-120b through OpenRouter routing)",
        stage="classification",
        cause="the serving provider returned a malformed answer with confidence 0",
        what_happened=(
            "The only line (wireless headphones) was served by CoreWeave (fp4), whose answer had "
            "`confidence: 0`, stray whitespace and no reasoning. EXC-03 treated the line as "
            "uncertain and the engine left it out, so TECH-01 (high) and DOC-03 (medium) did not "
            "fire and the receipt went to review instead of flag. The same provider made "
            "RCP-032 miss TECH-04, without changing its disposition. The first diagnosis blamed "
            "the EXC-03 threshold; checking the line's confidence showed it was 0, so no "
            "threshold would have helped (AI_NOTES 42)."
        ),
        change=(
            "Done: requests ignore CoreWeave, and its answers were asked again (ADR 0004, "
            "decided by Luis on dev-set evidence). Better next: treat 'confidence 0 and no "
            "reasoning' as a failed answer and retry through another provider, instead of "
            "keeping a blocklist."
        ),
        evidence="docs/decisions/0004-openrouter-routing.md (amendment), AI_NOTES 42",
    ),
)


def render_failure_cases(cases: tuple[FailureCase, ...]) -> list[str]:
    lines = [
        "The final run has no disposition error on the 28 scored receipts. These are the two "
        "the system made in earlier runs; both come from the classification stage, not from the "
        "rule logic.",
        "",
    ]
    for number, case in enumerate(cases, start=1):
        lines += [
            f"- **Failure case {number}: {case.receipt_id}**, stage `{case.stage}` "
            f"({case.cause}). Run: {case.run}.",
            f"  - What happened: {case.what_happened}",
            f"  - What I would change: {case.change}",
            f"  - Evidence: {case.evidence}.",
        ]
    lines.append("")
    return lines
