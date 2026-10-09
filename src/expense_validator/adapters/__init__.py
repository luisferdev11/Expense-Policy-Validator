"""Adapters: everything that touches the outside world (ADR 0003).

Files (receipts with the labels firewall, config, outputs, classification cache), the model
gateway (OpenRouter), the keyword baseline and tracing (Langfuse). Adapters implement ports and
may import the domain, but never the application layer.
"""
