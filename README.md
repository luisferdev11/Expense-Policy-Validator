# Expense Policy Validator

Reads itemized expense receipts, classifies every line item into a spend category, checks each
receipt against written expense policies with a deterministic rule engine, and raises
evidence-grounded exceptions with a final disposition of flag, review or pass.

**Status:** work in progress.

## Setup

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12.

```bash
uv sync
cp .env.example .env   # then set OPENROUTER_API_KEY
uv run pre-commit install
```
