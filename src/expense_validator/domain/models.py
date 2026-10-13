"""Typed interfaces between the pipeline components (data-model.md, research R1).

Every model is frozen. Input models forbid extra keys, which is a second labels firewall: an
answer key that survived the loader would fail validation. Money inside the pipeline is
`Decimal` (research R2); output models carry only JSON-native types.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from expense_validator.domain.taxonomy import Category

Language = Literal["en", "es", "fr", "de", "pt", "ja"]
Entity = Literal["GLOBAL", "APAC", "EMEA"]
Subtype = Literal["event_ticket", "mobile_handset", "prescription_medication", "none"]
RecipientKind = Literal["none", "client_or_prospect", "employee", "government_official"]
Severity = Literal["critical", "high", "medium", "low"]
Disposition = Literal["flag", "review", "pass"]
ClassificationStatus = Literal["classified", "unclassified"]


class _Frozen(BaseModel):
    model_config = ConfigDict(
        frozen=True, extra="forbid", json_schema_serialization_defaults_required=True
    )


# Inputs (produced by loader.py, answer fields already stripped)


class LineItemInput(_Frozen):
    line_id: str
    description_raw: str
    language: Language
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal
    amount: Decimal
    amount_usd: Decimal


class ReceiptInput(_Frozen):
    receipt_id: str
    employee_id: str
    employee_country: str
    entity: Entity
    submitted_expense_type: str
    merchant_name: str | None
    mcc: int
    mcc_description: str
    transaction_datetime: datetime | None
    currency: str | None
    fx_rate_to_usd: Decimal | None
    total_amount: Decimal | None
    total_amount_usd: Decimal | None
    attendee_count: int | None
    trip_id: str | None
    trip_nights: int | None
    pre_approval_ref: str | None
    itemized: bool
    vat_number: str | None = None
    line_items: tuple[LineItemInput, ...]


# Pipeline intermediates


class NormalisedItem(_Frozen):
    line_id: str
    description_raw: str
    description_clean: str
    language: Language


class ClassifierRequest(_Frozen):
    """Everything the classifier may see. Never the declared type or the attendee count."""

    description_clean: str
    merchant_name: str
    mcc: int


class ClassificationSource(_Frozen):
    classifier: str
    model_id: str
    provider_endpoint: str
    prompt_version: str
    cache_key: str
    request_id: str | None
    cost_usd: float | None
    prompt_tokens: int | None
    completion_tokens: int | None
    cache_hit: bool
    served_by: str | None = None


class Classification(_Frozen):
    line_id: str
    status: ClassificationStatus
    category: Category | None
    restricted: bool | None
    confidence: float | None = Field(default=None, ge=0, le=1)
    subtype: Subtype = "none"
    recipient_kind: RecipientKind = "none"
    recipient_name: str | None = None
    unclassified_reason: str | None = None
    source: ClassificationSource

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.status == "classified":
            if self.category is None or self.restricted is None or self.confidence is None:
                raise ValueError("a classified item needs category, restricted and confidence")
            if self.unclassified_reason is not None:
                raise ValueError("a classified item has no unclassified_reason")
        else:
            if self.category is not None:
                raise ValueError("an unclassified item has no category")
            if not self.unclassified_reason:
                raise ValueError("an unclassified item needs its reason")
        if self.subtype != "none" and self.category != "other":
            raise ValueError("subtype must be 'none' unless category is 'other' (A6)")
        return self


class CacheEntry(_Frozen):
    """One billed model answer, kept literally. It is parsed on every read, so a parser change
    never needs a new paid call and a schema violation replays identically offline."""

    cache_key: str
    content: str | None
    model_id: str
    provider_endpoint: str
    prompt_version: str
    request_id: str | None
    cost_usd: float | None
    prompt_tokens: int | None
    completion_tokens: int | None
    reasoning: str | None
    served_by: str | None = None


class ClassifiedReceipt(_Frozen):
    receipt: ReceiptInput
    classifications: tuple[Classification, ...]

    @model_validator(mode="after")
    def _aligned(self) -> Self:
        expected = [item.line_id for item in self.receipt.line_items]
        actual = [c.line_id for c in self.classifications]
        if expected != actual:
            raise ValueError("classifications must align with line items by line_id")
        return self


class MealContribution(_Frozen):
    receipt_id: str
    per_person_usd: Decimal
    international: bool
    cap_basis: Literal["global", "apac", "emea"]
    eur_rate_to_usd: Decimal | None


class CrossReceiptContext(_Frozen):
    """Aggregates that span receipts. An explicit engine input, never hidden state."""

    meal_days: dict[str, tuple[MealContribution, ...]] = Field(default_factory=dict)
    trip_otc_usd: dict[str, Decimal] = Field(default_factory=dict)


class RuleSet(_Frozen):
    rule_ids: tuple[str, ...]


# Engine output


class ExceptionFinding(_Frozen):
    rule_id: str
    policy_doc: str
    severity: Severity
    line_ids: list[str]
    evidence: str
    explanation: str
    decisions: list[str]
    computed: dict[str, str]


class ReviewSignal(_Frozen):
    rule_id: str
    policy_doc: str
    reason: str
    line_ids: list[str] = Field(default_factory=list)


class EngineFindings(_Frozen):
    exceptions: tuple[ExceptionFinding, ...]
    review_signals: tuple[ReviewSignal, ...]
    disposition: Disposition


# Output: one line per receipt in outputs/results.jsonl


class OutputLineItem(_Frozen):
    line_id: str
    description_raw: str
    category: Category | None
    restricted: bool | None
    confidence: float | None
    subtype: Subtype
    recipient_kind: RecipientKind
    recipient_name: str | None
    status: ClassificationStatus
    unclassified_reason: str | None


class RunMetadata(_Frozen):
    classifier: str
    model_id: str
    provider_endpoint: str
    prompt_version: str
    rules_version: str
    exc03_threshold: float
    exc03_threshold_status: Literal["provisional", "chosen_on_dev"]
    confidence_source: str = "self_reported"
    pipeline_config_version: str | None = None


class ReceiptResult(_Frozen):
    receipt_id: str
    disposition: Disposition
    line_items: list[OutputLineItem]
    exceptions: list[ExceptionFinding]
    review_signals: list[ReviewSignal]
    run: RunMetadata
