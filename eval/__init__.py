"""Evaluation package: the only code allowed to read the answer fields.

It reads `labels`, `line_items[].labels` and `notes` from `data/receipts.jsonl` to score the
committed pipeline outputs. Nothing in the pipeline package imports it, except the lazy import
inside the `epv eval` subcommand (analysis I2).
"""
