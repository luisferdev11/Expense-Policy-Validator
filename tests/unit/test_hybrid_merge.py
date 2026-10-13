"""The hybrid classifier's merge table, one test per row (spec 007, T014).

Both sides are the real adapters over fake transports and one JSONL cache, so the counters, the
generations and the composite source are the real ones. No network, no billed call.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from expense_validator.adapters.classification_cache import ClassificationCache
from expense_validator.adapters.hybrid_classifier import HybridClassifier
from expense_validator.adapters.openrouter.classifier import OpenRouterClassifier
from expense_validator.adapters.openrouter.decision_classifier import DecisionClassifier
from expense_validator.adapters.openrouter.models import REFERENCE
from expense_validator.app.pipeline import classify_receipt
from expense_validator.domain.models import ClassifierRequest
from tests.factories import item, receipt
from tests.fakes import RecordingTracer


def req(text: str) -> ClassifierRequest:
    return ClassifierRequest(description_clean=text, merchant_name="Shop", mcc=5999)


def jev_body(n: int, choice: str | None, top: float = 0.9) -> dict[str, Any]:
    category: dict[str, Any] = {"choice": choice, "probabilities": {choice: top}}
    return {
        "id": f"jev-{n}",
        "provider": "typesafe",
        "answers": {"category": category},
        "usage": {"input_tokens": 700, "output_tokens": 10, "cost": 0.00001},
    }


def chat_body(
    n: int,
    category: str = "food_beverage",
    subtype: str = "none",
    kind: str = "none",
    name: str | None = None,
    raw: str | None = None,
) -> dict[str, Any]:
    answer = {
        "category": category,
        "confidence": 0.8,
        "subtype": subtype,
        "recipient_kind": kind,
        "recipient_name": name,
    }
    return {
        "id": f"chat-{n}",
        "provider": "DeepInfra",
        "choices": [{"message": {"content": raw if raw is not None else json.dumps(answer)}}],
        "usage": {"prompt_tokens": 600, "completion_tokens": 40, "cost": 0.00004},
    }


class ByItem:
    """A fake transport: the response (or exception) for each item text."""

    def __init__(self, answers: dict[str, Any], decision: bool) -> None:
        self.answers = answers
        self.decision = decision
        self.calls = 0

    def __call__(self, payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
        self.calls += 1
        if self.decision:
            text = payload["state"]["item"]
        else:
            text = payload["messages"][1]["content"].splitlines()[0].removeprefix("Item: ")
        found = self.answers[text]
        if isinstance(found, Exception):
            raise found
        body = found(self.calls) if callable(found) else found
        return body, json.dumps(body)


def make(
    tmp_path: Path,
    jev: dict[str, Any],
    chat: dict[str, Any],
    *,
    offline: bool = False,
    jev_cap: float = 1.0,
    chat_cap: float = 1.0,
    cache: ClassificationCache | None = None,
) -> tuple[HybridClassifier, RecordingTracer, ByItem, ByItem]:
    tracer = RecordingTracer()
    cache = cache or ClassificationCache(tmp_path / "cache.jsonl")
    jev_transport = ByItem(jev, decision=True)
    chat_transport = ByItem(chat, decision=False)
    hybrid = HybridClassifier(
        DecisionClassifier(
            cache,
            tracer,
            transport=jev_transport,
            offline=offline,
            cap_usd=jev_cap,
            raw_dir=tmp_path / "raw",
        ),
        OpenRouterClassifier(
            cache,
            tracer,
            transport=chat_transport,
            offline=offline,
            cap_usd=chat_cap,
            raw_dir=tmp_path / "raw",
            pin=REFERENCE,
        ),
    )
    return hybrid, tracer, jev_transport, chat_transport


def test_row_1_a_category_other_than_other_takes_the_chat_recipient(tmp_path: Path) -> None:
    hybrid, _, _, _ = make(
        tmp_path,
        {"gift": jev_body(1, "gift", top=0.93)},
        {"gift": chat_body(1, "food_beverage", kind="client_or_prospect", name="Acme Corp")},
    )
    c = hybrid.classify("L1", req("gift"))
    assert (c.status, c.category, c.confidence) == ("classified", "gift", 0.93)
    assert c.restricted is True
    assert c.subtype == "none"
    assert (c.recipient_kind, c.recipient_name) == ("client_or_prospect", "Acme Corp")
    assert hybrid.last_flags == {}


def test_row_2_both_say_other_so_the_chat_subtype_is_kept(tmp_path: Path) -> None:
    hybrid, _, _, _ = make(
        tmp_path,
        {"ticket": jev_body(1, "other")},
        {"ticket": chat_body(1, "other", subtype="event_ticket", kind="employee")},
    )
    c = hybrid.classify("L1", req("ticket"))
    assert (c.category, c.subtype, c.recipient_kind) == ("other", "event_ticket", "employee")
    assert hybrid.last_flags == {}


def test_row_3_jev_other_chat_not_other_is_a_conflict_with_subtype_none(tmp_path: Path) -> None:
    hybrid, _, _, _ = make(
        tmp_path,
        {"thing": jev_body(1, "other", top=0.7)},
        {"thing": chat_body(1, "food_beverage", kind="client_or_prospect", name="Acme")},
    )
    c = hybrid.classify("L1", req("thing"))
    assert (c.category, c.confidence, c.subtype) == ("other", 0.7, "none")
    assert (c.recipient_kind, c.recipient_name) == ("client_or_prospect", "Acme")
    assert hybrid.last_flags == {"hybrid_conflict": True}


def test_row_4_a_chat_schema_violation_keeps_jev_and_zeroes_the_detail(tmp_path: Path) -> None:
    hybrid, tracer, _, _ = make(
        tmp_path,
        {"beer": jev_body(1, "alcohol")},
        {"beer": chat_body(1, raw='{"category": "beer"}')},
    )
    c = hybrid.classify("L1", req("beer"))
    assert (c.status, c.category, c.restricted) == ("classified", "alcohol", True)
    assert (c.subtype, c.recipient_kind, c.recipient_name) == ("none", "none", None)
    assert hybrid.last_flags == {"detail_violation": True}
    again = hybrid.classify("L1", req("beer"))  # replayed: the violation stays one
    assert again.source.cache_hit is True
    assert hybrid.last_flags == {"detail_violation": True}
    assert len(tracer.named("classify-item")) == 2


def test_row_5_a_jev_schema_violation_is_unclassified_whatever_the_chat_says(
    tmp_path: Path,
) -> None:
    hybrid, _, _, _ = make(
        tmp_path, {"x": jev_body(1, "moonbeams")}, {"x": chat_body(1, "food_beverage")}
    )
    c = hybrid.classify("L1", req("x"))
    assert (c.status, c.unclassified_reason) == ("unclassified", "schema_violation")
    assert c.category is None


def test_row_6_a_transient_jev_failure_is_reported_as_it_is(tmp_path: Path) -> None:
    hybrid, _, _, _ = make(
        tmp_path, {"x": ConnectionError("down")}, {"x": chat_body(1, "food_beverage")}
    )
    c = hybrid.classify("L1", req("x"))
    assert (c.status, c.unclassified_reason) == ("unclassified", "gateway_error")
    # a refused jev call (its own cap) is transient as well
    refused, _, _, _ = make(
        tmp_path / "b", {"x": jev_body(1, "alcohol")}, {"x": chat_body(1)}, jev_cap=0.0
    )
    assert refused.classify("L1", req("x")).unclassified_reason == "budget_refused"


def test_row_7_a_transient_chat_failure_is_reported_as_it_is(tmp_path: Path) -> None:
    hybrid, _, _, _ = make(tmp_path, {"x": jev_body(1, "alcohol")}, {"x": ConnectionError("down")})
    c = hybrid.classify("L1", req("x"))
    assert (c.status, c.unclassified_reason) == ("unclassified", "gateway_error")
    refused, _, _, _ = make(
        tmp_path / "b", {"x": jev_body(1, "alcohol")}, {"x": chat_body(1)}, chat_cap=0.0
    )
    assert refused.classify("L1", req("x")).unclassified_reason == "budget_refused"


def test_row_8_an_offline_miss_on_either_side_is_an_offline_miss(tmp_path: Path) -> None:
    both, _, jev, chat = make(
        tmp_path, {"x": jev_body(1, "alcohol")}, {"x": chat_body(1)}, offline=True
    )
    c = both.classify("L1", req("x"))
    assert (c.status, c.unclassified_reason) == ("unclassified", "offline_cache_miss")
    assert jev.calls == chat.calls == 0
    # jev answered earlier and is cached; the chat side misses offline
    cache = ClassificationCache(tmp_path / "shared.jsonl")
    live, _, _, _ = make(
        tmp_path / "live", {"y": jev_body(2, "alcohol")}, {"y": chat_body(2)}, cache=cache
    )
    live.category_source.classify("L1", req("y"))
    half, _, _, _ = make(tmp_path / "half", {}, {}, offline=True, cache=cache)
    only_jev_cached = half.classify("L1", req("y"))
    assert only_jev_cached.unclassified_reason == "offline_cache_miss"


def test_the_merged_source_is_a_composite_in_category_then_detail_order(tmp_path: Path) -> None:
    hybrid, _, _, _ = make(
        tmp_path, {"beer": jev_body(1, "alcohol")}, {"beer": chat_body(1, "alcohol")}
    )
    c = hybrid.classify("L1", req("beer"))
    s = c.source
    jev_key, chat_key = hybrid.last_keys or ("", "")
    assert s.classifier == "hybrid"
    assert s.model_id == "typesafe/jev-1.13+openai/gpt-oss-120b"
    assert s.provider_endpoint == "openrouter"
    assert s.prompt_version == "hyb-v1(dec-v1+cls-v2)"
    assert s.cache_key == hashlib.sha256(f"{jev_key}+{chat_key}".encode()).hexdigest()
    assert s.request_id == "jev-1+chat-1"
    assert s.served_by == "typesafe+DeepInfra"
    assert s.cost_usd == 0.00005
    assert (s.prompt_tokens, s.completion_tokens) == (1300, 50)
    assert s.cache_hit is False
    assert hybrid.model_id == s.model_id


def test_a_replay_is_identical_and_makes_no_call_and_no_generation(tmp_path: Path) -> None:
    hybrid, tracer, jev, chat = make(
        tmp_path, {"beer": jev_body(1, "alcohol")}, {"beer": chat_body(1, "alcohol")}
    )
    first = hybrid.classify("L1", req("beer"))
    assert len(tracer.named("classify-item")) == 2  # one per billed side, none named after a model
    assert {g.name for g in tracer.observations} == {"classify-item"}
    again = hybrid.classify("L1", req("beer"))
    assert (jev.calls, chat.calls) == (1, 1)
    assert len(tracer.named("classify-item")) == 2
    assert again.source.cache_hit is True
    assert again.model_copy(update={"source": first.source}) == first
    assert again.source == first.source.model_copy(update={"cache_hit": True})


def test_cache_hit_is_true_only_when_both_sides_hit(tmp_path: Path) -> None:
    cache = ClassificationCache(tmp_path / "shared.jsonl")
    chat_only = OpenRouterClassifier(
        cache,
        RecordingTracer(),
        transport=ByItem({"x": chat_body(7, "alcohol")}, decision=False),
        raw_dir=tmp_path / "raw",
    )
    chat_only.classify("L1", req("x"))  # the detail side's answer is already cached
    hybrid, _, jev, chat = make(
        tmp_path, {"x": jev_body(1, "alcohol")}, {"x": chat_body(8)}, cache=cache
    )
    c = hybrid.classify("L1", req("x"))
    assert (jev.calls, chat.calls) == (1, 0)
    assert c.source.cache_hit is False
    assert c.source.request_id == "jev-1+chat-7"


def test_counters_are_the_sums_of_both_sides(tmp_path: Path) -> None:
    hybrid, _, _, _ = make(
        tmp_path,
        {"a": jev_body(1, "alcohol"), "b": jev_body(2, "alcohol")},
        {"a": chat_body(1), "b": chat_body(2)},
    )
    hybrid.classify("L1", req("a"))
    hybrid.classify("L2", req("b"))
    hybrid.classify("L3", req("a"))
    assert hybrid.calls_made == 4
    assert hybrid.cache_hits == 2
    assert round(hybrid.run_spend_usd, 6) == 0.0001


def test_each_side_has_its_own_cap(tmp_path: Path) -> None:
    # jev's cap is reached by its first call; the chat side still bills for the same line
    hybrid, _, jev, chat = make(
        tmp_path,
        {"a": jev_body(1, "alcohol"), "b": jev_body(2, "alcohol")},
        {"a": chat_body(1), "b": chat_body(2)},
        jev_cap=0.000005,
    )
    assert hybrid.classify("L1", req("a")).status == "classified"
    second = hybrid.classify("L2", req("b"))
    assert second.unclassified_reason == "budget_refused"
    assert jev.calls == 1
    assert chat.calls == 2  # the category side is asked first, and the chat side still answers


def test_flags_are_reset_on_every_call(tmp_path: Path) -> None:
    hybrid, _, _, _ = make(
        tmp_path,
        {"thing": jev_body(1, "other"), "beer": jev_body(2, "alcohol")},
        {"thing": chat_body(1, "food_beverage"), "beer": chat_body(2, "alcohol")},
    )
    hybrid.classify("L1", req("thing"))
    assert hybrid.last_flags == {"hybrid_conflict": True}
    hybrid.classify("L2", req("beer"))
    assert hybrid.last_flags == {}


def test_the_classify_receipt_span_reports_a_flag_only_on_the_line_that_raised_it(
    tmp_path: Path,
) -> None:
    hybrid, _, _, _ = make(
        tmp_path,
        {"thing": jev_body(1, "other"), "beer": jev_body(2, "alcohol")},
        {"thing": chat_body(1, "food_beverage"), "beer": chat_body(2, "alcohol")},
    )
    r = receipt([item(1, description="thing"), item(2, description="beer")])
    tracer = RecordingTracer()
    classify_receipt(r, hybrid, tracer, "run")
    (span,) = tracer.named("classify-receipt")
    lines = {line["line_id"]: line for line in span.updates[-1]["output"]}
    assert lines["SYN-1-L1"]["hybrid_conflict"] is True
    assert "hybrid_conflict" not in lines["SYN-1-L2"]
    assert "detail_violation" not in lines["SYN-1-L1"]
