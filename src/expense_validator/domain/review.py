"""Review rules of the lifecycle: the quality-review sample (ADR 0007 D12).

Reviewer reason codes, the agreement score and the human classification are added here with the
reviewer actions.
"""

from __future__ import annotations

import hashlib

QA_SAMPLE_ONE_IN = 10


def qa_sampled(receipt_id: str, revision: int) -> bool:
    """Whether an auto-approved receipt goes to quality review: about one in ten, chosen by a
    hash of the receipt and revision, so it is reproducible and needs no randomness."""
    digest = hashlib.sha256(f"{receipt_id}:{revision}".encode()).hexdigest()
    return int(digest, 16) % QA_SAMPLE_ONE_IN == 0
