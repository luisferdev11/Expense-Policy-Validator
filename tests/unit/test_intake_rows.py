"""Rows of an upload that are valid JSON but not receipts, and exact money in arrays.

The viewer's upload (iteration 2.1) and the API's batches share one row parser, so a row that is
not a JSON object is reported with its row number instead of raising.
"""

from __future__ import annotations

import json
from decimal import Decimal

from expense_validator.app.intake import parse_upload, split_rows
from tests.support import receipt_json


def test_a_row_that_is_valid_json_but_not_an_object_is_reported_with_its_number() -> None:
    upload = receipt_json("SYN-1") + "\n42\n" + receipt_json("SYN-2") + "\n"
    parsed = parse_upload(upload)
    assert [r.receipt_id for r in parsed.receipts] == ["SYN-1", "SYN-2"]
    assert parsed.errors == [(2, "a receipt is a JSON object")]


def test_a_json_array_with_a_non_object_element_reports_that_element() -> None:
    upload = "[" + receipt_json("SYN-1") + ', "text", null]'
    parsed = parse_upload(upload)
    assert len(parsed.receipts) == 1
    assert [row for row, _ in parsed.errors] == [2, 3]


def test_money_in_a_json_array_keeps_its_written_precision() -> None:
    body = json.loads(receipt_json("SYN-1"))
    body["total_amount"] = 0.10  # written as 0.1
    text = json.dumps([body]).replace("0.1,", "0.1000000000000000055511151231257827,")
    parsed = parse_upload(text)
    assert parsed.receipts[0].total_amount == Decimal("0.1000000000000000055511151231257827")


def test_split_rows_handles_each_upload_shape() -> None:
    one = receipt_json("SYN-1")
    assert len(split_rows(one)) == 1
    assert len(split_rows(one + "\n" + one + "\n")) == 2
    assert len(split_rows("[" + one + "," + one + "]")) == 2
    assert split_rows("   \n ") == []
