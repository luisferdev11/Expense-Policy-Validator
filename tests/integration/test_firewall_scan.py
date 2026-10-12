"""No answer key reaches the store, an API response or a trace (rule 1, FR-010, SC-007).

The 32 receipts are submitted with answer keys in the request body, so the keys really arrive.
The bodies are built from the stripping loader plus **invented** answer keys carrying a marker:
no test reads the real answers (only `eval/` does). After processing, the whole database, every
endpoint's response and every trace input and output are scanned for the keys and the marker.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from typing import Any

import pytest
from fastapi.testclient import TestClient

from expense_validator.adapters.config_files import load_pipeline_config
from expense_validator.adapters.receipts_file import load_receipts
from expense_validator.adapters.sqlite_cache import SqliteClassificationCache
from expense_validator.adapters.sqlite_store import utc_now
from expense_validator.app.api import create_app
from expense_validator.paths import CLASSIFICATIONS_FILE
from tests.fakes import RecordingTracer
from tests.integration.test_api_parity import offline_classifier
from tests.support import Stack, build_stack

MARKER = "INVENTED-ANSWER-KEY"
KEYS = ('"labels"', '"notes"', '"expected_exceptions"', MARKER)


def raw_lines() -> list[str]:
    """The dataset as request bodies that carry answer keys: the receipts come from the
    stripping loader, and the keys, which are invented, are added to every receipt and line."""
    lines = []
    for receipt in load_receipts():
        body = receipt.model_dump(mode="json")
        body["labels"] = {"disposition": MARKER}
        body["notes"] = MARKER
        for line in body["line_items"]:
            line["labels"] = {"category": MARKER}
        lines.append(json.dumps(body))
    return lines


@pytest.fixture(scope="module")
def processed(tmp_path_factory: pytest.TempPathFactory) -> tuple[Stack, RecordingTracer, list[str]]:
    directory = tmp_path_factory.mktemp("firewall")
    tracer = RecordingTracer()
    stack = build_stack(directory, tracer)
    # The answer table is part of the database that is scanned below.
    SqliteClassificationCache(stack.store.path, utc_now).seed_from(CLASSIFICATIONS_FILE)
    worker = stack.worker(offline_classifier(directory), tracer, config=load_pipeline_config())
    lines = raw_lines()
    assert all(any(key in line for key in KEYS) for line in lines)  # the keys do arrive
    client = TestClient(create_app(stack.service))
    for line in lines:
        response = client.post(
            "/receipts", content=line, headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 202
    worker.run_once()
    return stack, tracer, lines


def found_in(text: str) -> list[str]:
    return [key for key in KEYS if key in text]


def test_the_database_holds_no_answer_key(
    processed: tuple[Stack, RecordingTracer, list[str]],
) -> None:
    stack, _, _ = processed
    with closing(sqlite3.connect(stack.store.path)) as conn:
        dump = "\n".join(conn.iterdump())
    assert len(dump) > 100_000  # it really holds the processed dataset
    assert found_in(dump) == []


def test_the_answer_table_holds_model_answers_and_no_answer_key(
    processed: tuple[Stack, RecordingTracer, list[str]],
) -> None:
    stack, _, _ = processed
    with closing(sqlite3.connect(stack.store.path)) as conn:
        rows = [r[0] for r in conn.execute("SELECT entry FROM classification_cache")]
    assert len(rows) == 78  # the seeded answers are in the scanned database
    assert found_in("\n".join(rows)) == []


def test_every_response_is_free_of_answer_keys(
    processed: tuple[Stack, RecordingTracer, list[str]],
) -> None:
    stack, _, lines = processed
    client = TestClient(create_app(stack.service))
    seen: list[str] = [client.get("/receipts", params={"limit": 100}).text]
    for line in lines:
        rid = json.loads(line)["receipt_id"]
        for path in (f"/receipts/{rid}", f"/receipts/{rid}/events", f"/receipts/{rid}/revisions/1"):
            seen.append(client.get(path).text)
    assert len(seen) == 1 + 3 * 32
    assert found_in("\n".join(seen)) == []


def test_every_trace_input_and_output_is_free_of_answer_keys(
    processed: tuple[Stack, RecordingTracer, list[str]],
) -> None:
    _, tracer, _ = processed
    assert tracer.observations  # something was traced

    def dump(value: Any) -> str:
        return json.dumps(value, default=str)

    text = "\n".join(dump([o.fields, o.updates]) for o in tracer.observations)
    assert found_in(text) == []


def test_the_stored_receipts_are_exactly_what_the_loader_hands_the_pipeline(
    processed: tuple[Stack, RecordingTracer, list[str]],
) -> None:
    stack, _, _ = processed
    for expected in load_receipts():
        with stack.store.transaction(write=False) as tx:
            stored = tx.get_revision(expected.receipt_id, 1)
        assert stored is not None and stored.receipt == expected
