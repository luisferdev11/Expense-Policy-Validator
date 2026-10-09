"""The classifier never sees the declared type or the attendee count (T021, FR-007)."""

from expense_validator.adapters.openrouter.prompt import messages
from expense_validator.adapters.receipts_file import load_receipts
from expense_validator.domain.models import ClassifierRequest
from expense_validator.domain.normaliser import normalise
from expense_validator.ports.classifier import build_request


def test_request_has_only_three_fields() -> None:
    assert set(ClassifierRequest.model_fields) == {"description_clean", "merchant_name", "mcc"}


def test_user_message_is_exactly_the_three_fields() -> None:
    for r in load_receipts():
        for norm in normalise(r):
            req = build_request(r, norm)
            system, user = messages(req)
            assert system["role"] == "system"
            assert user["content"] == (
                f"Item: {req.description_clean}\nMerchant: {req.merchant_name}\nMCC: {req.mcc}"
            )


def test_system_prompt_does_not_depend_on_the_receipt() -> None:
    receipts = load_receipts()
    systems = {messages(build_request(r, n))[0]["content"] for r in receipts for n in normalise(r)}
    assert len(systems) == 1
