"""Load test of the API (spec 006, US5): Locust scenarios, profiles and a report generator.

Top-level package like `eval/`, outside `src/`: never imported by the application. The receipts it
sends are built from `docs/samples/receipt-one.json`; nothing here reads `data/receipts.jsonl`.
"""
