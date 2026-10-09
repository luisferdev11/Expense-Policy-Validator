"""Ports: the interfaces the application depends on (ADR 0003).

`classifier.ItemClassifier` (OpenRouter, keyword baseline, test fakes) and `tracer.Tracer`
(Langfuse, no-op). Ports import only the domain.
"""
