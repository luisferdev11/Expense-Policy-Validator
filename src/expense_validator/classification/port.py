"""The ItemClassifier port and the construction of its request (FR-007).

A request carries only the cleaned description, the merchant name and the MCC. The declared
expense type and the attendee count never reach a classifier.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from expense_validator.models import (
    Classification,
    ClassifierRequest,
    NormalisedItem,
    ReceiptInput,
)


@runtime_checkable
class ItemClassifier(Protocol):
    name: str
    model_id: str
    provider_endpoint: str
    prompt_version: str

    def classify(self, line_id: str, request: ClassifierRequest) -> Classification: ...


def build_request(receipt: ReceiptInput, item: NormalisedItem) -> ClassifierRequest:
    return ClassifierRequest(
        description_clean=item.description_clean,
        merchant_name=receipt.merchant_name or "",
        mcc=receipt.mcc,
    )
