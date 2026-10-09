"""keyword-flagger: the legacy kind of system this project replaces (FR-032).

Any restricted keyword on any line flags the receipt; otherwise it passes. It reuses the
restricted-category lists of the keyword-classifier and reads inputs through the loader only.
It produces dispositions and a per-line restricted flag, no categories: macro F1 is n/a.
"""

from __future__ import annotations

from pathlib import Path

from expense_validator.adapters.keyword_classifier import KEYWORDS, matches
from expense_validator.adapters.receipts_file import load_receipts
from expense_validator.adapters.results_files import write_results
from expense_validator.domain.models import (
    Disposition,
    OutputLineItem,
    ReceiptInput,
    ReceiptResult,
    RunMetadata,
)
from expense_validator.domain.normaliser import clean
from expense_validator.domain.taxonomy import restricted_for

RESTRICTED_WORDS = tuple(w for c, words in KEYWORDS.items() if restricted_for(c) for w in words)
RUN = RunMetadata(
    classifier="keyword-flagger",
    model_id="keyword-lists",
    provider_endpoint="none",
    prompt_version="kw-v1",
    rules_version="none",
    exc03_threshold=0.0,
    exc03_threshold_status="provisional",
)


def flagged_lines(receipt: ReceiptInput) -> set[str]:
    return {
        item.line_id
        for item in receipt.line_items
        if any(matches(w, clean(item.description_raw).casefold()) for w in RESTRICTED_WORDS)
    }


def flag_receipt(receipt: ReceiptInput) -> Disposition:
    return "flag" if flagged_lines(receipt) else "pass"


def run_flagger(path: Path) -> list[ReceiptResult]:
    results = []
    for r in sorted(load_receipts(), key=lambda x: x.receipt_id):
        flagged = flagged_lines(r)
        results.append(
            ReceiptResult(
                receipt_id=r.receipt_id,
                disposition=flag_receipt(r),
                line_items=[
                    OutputLineItem(
                        line_id=i.line_id,
                        description_raw=i.description_raw,
                        category=None,
                        restricted=i.line_id in flagged,
                        confidence=None,
                        subtype="none",
                        recipient_kind="none",
                        recipient_name=None,
                        status="classified",
                        unclassified_reason=None,
                    )
                    for i in r.line_items
                ],
                exceptions=[],
                review_signals=[],
                run=RUN,
            )
        )
    write_results(path, results)
    return results
