"""One factory for the configured item classifier (spec 007, FR-024, FR-025).

`default_classifier` (uploads and the viewer), `build_worker` (the backend) and `epv run` all
build their classifier here, so switching it is one configuration value, `classifier_model` in
`config/pipeline.yaml`. A name in `PINS` builds today's chat classifier with unchanged behaviour;
`jev-1.13` builds the decision classifier (category only); `jev-hybrid` builds the hybrid.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from expense_validator.adapters.classification_cache import ClassificationCache
from expense_validator.adapters.hybrid_classifier import HybridClassifier
from expense_validator.adapters.openrouter.classifier import CAP_USD, OpenRouterClassifier
from expense_validator.adapters.openrouter.classifier import Transport as ChatTransport
from expense_validator.adapters.openrouter.decision_classifier import DecisionClassifier
from expense_validator.adapters.openrouter.decision_classifier import Transport as DecisionTransport
from expense_validator.adapters.openrouter.models import (
    CLASSIFIER_NAMES,
    HYBRID,
    JEV,
    PINS,
    REFERENCE,
)
from expense_validator.adapters.openrouter.prompt_sync import sync_decision_prompt, sync_prompt
from expense_validator.adapters.tracing import GuardedTracer
from expense_validator.ports.classifier import ItemClassifier
from expense_validator.ports.tracer import Tracer

__all__ = ["CLASSIFIER_NAMES", "build_classifier", "sync_prompt_links"]

CHAT = "chat"
DECISION = "decision"


def sync_prompt_links(name: str, tracer: GuardedTracer, offline: bool) -> dict[str, Any]:
    """The Langfuse prompt links the named classifier needs, synced once; none when offline."""
    links: dict[str, Any] = {}
    if offline:
        return links
    if name in PINS or name == HYBRID:
        links[CHAT] = sync_prompt(tracer)
    if name in (JEV, HYBRID):
        links[DECISION] = sync_decision_prompt(tracer)
    return links


def build_classifier(
    name: str,
    tracer: Tracer,
    cache: ClassificationCache,
    *,
    offline: bool = False,
    prompt_links: Mapping[str, Any] | None = None,
    null_subtype_as_none: bool = False,
    cap_usd: float = CAP_USD,
    chat_transport: ChatTransport | None = None,
    decision_transport: DecisionTransport | None = None,
) -> ItemClassifier:
    """Build the classifier `name`. Both sides of the hybrid share `cache` (their keys differ) and
    each has its own spend cap, `cap_usd`."""
    links = prompt_links or {}
    if name in PINS:
        return OpenRouterClassifier(
            cache,
            tracer,
            transport=chat_transport,
            offline=offline,
            cap_usd=cap_usd,
            prompt_link=links.get(CHAT),
            pin=PINS[name],
            null_subtype_as_none=null_subtype_as_none,
        )
    if name == JEV:
        return DecisionClassifier(
            cache,
            tracer,
            transport=decision_transport,
            offline=offline,
            cap_usd=cap_usd,
            prompt_link=links.get(DECISION),
        )
    if name == HYBRID:
        return HybridClassifier(
            DecisionClassifier(
                cache,
                tracer,
                transport=decision_transport,
                offline=offline,
                cap_usd=cap_usd,
                prompt_link=links.get(DECISION),
            ),
            OpenRouterClassifier(
                cache,
                tracer,
                transport=chat_transport,
                offline=offline,
                cap_usd=cap_usd,
                prompt_link=links.get(CHAT),
                pin=REFERENCE,
                null_subtype_as_none=null_subtype_as_none,
            ),
        )
    raise ValueError(f"unknown classifier {name!r}; accepted: {', '.join(CLASSIFIER_NAMES)}")
