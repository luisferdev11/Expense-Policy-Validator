"""Expense Policy Validator: the pipeline package.

Five components behind typed interfaces (ADR 0002): normaliser, item classifier, policy
retriever, policy engine and exception reporter, plus the loader, tracing and the CLI.

Labels firewall: nothing in this package reads the answer fields of `data/receipts.jsonl`.
Only `loader.py` names them, to strip them. Only the separate `eval` package reads answers.
"""
