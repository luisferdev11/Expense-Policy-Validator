"""Builds the Postman collection and environment of the backend (iteration 3).

Run from the repository root:

    uv run python docs/api/build_collection.py

The collection is generated so that its receipts, assertions and order stay readable and
consistent. It writes `epv.postman_collection.json` and `epv.local.postman_environment.json`
next to this file.

The scenarios run offline: every line uses a (description, merchant, MCC) that is already in
the committed classification cache, so start the server with
`uv run epv serve --with-worker --offline --no-trace` and no model is called. The receipts are
synthetic copies of line shapes; they carry no answer keys, except one that carries invented
ones on purpose, to show that the backend discards them.

Every run uses its own `run` id in receipt and employee ids, so the collection can be run again
on the same database without earlier receipts joining the cross-receipt rules.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SCHEMA = "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"

# Lines whose classification is in the committed cache (description, merchant, MCC).
MEAL_LINE = ("Grilled salmon entree", "Harvest Table Kitchen", 5812, "Eating places")
MEAL_LINE_2 = ("Iced tea", "Harvest Table Kitchen", 5812, "Eating places")
OFFICE_LINE = ("Legal pads 3-pack", "Cornerstone Office Supply", 5943, "Office supply stores")
GIFT_LINE = (
    "Gift basket for R. Delgado, City Procurement Office",
    "Harbor View Restaurant",
    5812,
    "Eating places",
)


def rid(suffix: str) -> str:
    return "PM-{{run}}-" + suffix


def receipt(
    suffix: str,
    line: tuple[str, str, int, str],
    amount: float,
    expense_type: str = "Meals - Individual",
    employee: str = "E1",
    **extra: Any,
) -> dict[str, Any]:
    description, merchant, mcc, mcc_description = line
    receipt_id = rid(suffix)
    body: dict[str, Any] = {
        "receipt_id": receipt_id,
        "employee_id": "PM-{{run}}-" + employee,
        "employee_country": "US",
        "entity": "GLOBAL",
        "submitted_expense_type": expense_type,
        "merchant_name": merchant,
        "mcc": mcc,
        "mcc_description": mcc_description,
        "transaction_datetime": "2026-05-01T12:00:00",
        "currency": "USD",
        "fx_rate_to_usd": 1.0,
        "total_amount": amount,
        "total_amount_usd": amount,
        "attendee_count": None,
        "trip_id": None,
        "trip_nights": None,
        "pre_approval_ref": None,
        "itemized": True,
        "line_items": [
            {
                "line_id": receipt_id + "-L1",
                "description_raw": description,
                "language": "en",
                "quantity": 1,
                "unit_price": amount,
                "amount": amount,
                "amount_usd": amount,
            }
        ],
    }
    body.update(extra)
    return body


def script(lines: list[str]) -> dict[str, Any]:
    return {"type": "text/javascript", "exec": lines}


def request(
    name: str,
    method: str,
    path: str,
    *,
    body: Any = None,
    raw: str | None = None,
    content_type: str = "application/json",
    headers: dict[str, str] | None = None,
    query: dict[str, str] | None = None,
    tests: list[str] | None = None,
    prerequest: list[str] | None = None,
    description: str = "",
) -> dict[str, Any]:
    header = [{"key": k, "value": v} for k, v in (headers or {}).items()]
    item: dict[str, Any] = {"name": name, "request": {"method": method, "header": header}}
    if body is not None or raw is not None:
        header.append({"key": "Content-Type", "value": content_type})
        text = raw if raw is not None else json.dumps(body, indent=2)
        # A version variable is a number in the JSON, not a string.
        text = re.sub(r'"(\{\{\w*[eE]val\w*\}\})"', r"\1", text)
        item["request"]["body"] = {"mode": "raw", "raw": text}
    query_items = [{"key": k, "value": v} for k, v in (query or {}).items()]
    url_raw = "{{baseUrl}}" + path
    if query_items:
        url_raw += "?" + "&".join(f"{q['key']}={q['value']}" for q in query_items)
    url: dict[str, Any] = {
        "raw": url_raw,
        "host": ["{{baseUrl}}"],
        "path": [p for p in path.split("/") if p],
    }
    if query_items:
        url["query"] = query_items
    item["request"]["url"] = url
    if description:
        item["request"]["description"] = description
    events = []
    if prerequest:
        events.append({"listen": "prerequest", "script": script(prerequest)})
    if tests:
        events.append({"listen": "test", "script": script(tests)})
    if events:
        item["event"] = events
    return item


def folder(name: str, description: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    return {"name": name, "description": description, "item": items}


def status(code: int) -> str:
    return f'pm.test("status is {code}", () => pm.response.to.have.status({code}));'


def error_code(code: str) -> str:
    return (
        f'pm.test("error code is {code}", () => '
        f'pm.expect(pm.response.json().error.code).to.eql("{code}"));'
    )


def wait(
    name: str, path: str, done: str, then: list[str] | None = None, why: str = ""
) -> dict[str, Any]:
    """GET `path` until the JS condition `done` (over `body`) holds, then run `then`.

    The pre-request timer gives the worker time between polls; the request repeats itself with
    `setNextRequest` up to 40 times.
    """
    tests = [
        "const body = pm.response.json();",
        'const key = "polls " + pm.info.requestName;',
        "const polls = Number(pm.collectionVariables.get(key) || 0) + 1;",
        f"const done = Boolean({done});",
        "if (!done && polls < 40) {",
        "  pm.collectionVariables.set(key, polls);",
        "  postman.setNextRequest(pm.info.requestName);",
        "} else {",
        "  pm.collectionVariables.unset(key);",
        '  pm.test("processed in time", () => pm.expect(done, JSON.stringify(body)).to.be.true);',
        *(then or []),
        "}",
    ]
    return request(
        name,
        "GET",
        path,
        prerequest=["setTimeout(function () {}, 1200);"],
        tests=tests,
        description=why or "Polls until the worker has processed the receipt.",
    )


def rules(path: str = "body.result.exceptions") -> str:
    return f"{path}.map(e => e.rule_id)"


def act(
    name: str, receipt: str, action: str, fields: dict[str, Any], tests: list[str]
) -> dict[str, Any]:
    return request(
        name,
        "POST",
        f"/receipts/{rid(receipt)}/actions/{action}",
        body={"actor": "alice", **fields},
        tests=tests,
    )


RESTING = '["auto_approved", "in_review", "compliance"]'


def build() -> dict[str, Any]:
    office = receipt("OFFICE", OFFICE_LINE, 24.0, "Office Supplies", "EO")
    office_changed = receipt("OFFICE", OFFICE_LINE, 18.5, "Office Supplies", "EO")
    meal_a = receipt("MEAL-A", MEAL_LINE, 40.0)
    meal_b = receipt("MEAL-B", MEAL_LINE_2, 50.0)
    meal_c = receipt("MEAL-C", MEAL_LINE, 40.0, employee="E2")
    meal_d = receipt("MEAL-D", MEAL_LINE_2, 50.0, employee="E2")
    meal_d_answer = receipt("MEAL-D", MEAL_LINE_2, 50.0, employee="E2", attendee_count=2)
    gift = receipt("GIFT", GIFT_LINE, 85.0, "Client Entertainment", "E3")
    gift_2 = receipt("GIFT-2", GIFT_LINE, 90.0, "Client Entertainment", "E4")
    with_answers = receipt(
        "FIREWALL",
        OFFICE_LINE,
        12.0,
        "Office Supplies",
        "EF",
        labels={"disposition": "flag"},
        notes="invented answer key: it must never be stored",
    )
    with_answers["line_items"][0]["labels"] = {"category": "gift"}
    batch_rows = [
        receipt("BATCH-1", OFFICE_LINE, 10.0, "Office Supplies", "EB1"),
        receipt("BATCH-2", OFFICE_LINE, 11.0, "Office Supplies", "EB2"),
    ]
    batch_text = "\n".join(
        [json.dumps(batch_rows[0]), "{this row is not valid json", json.dumps(batch_rows[1])]
    )

    intake = folder(
        "1 Intake and idempotency",
        "Persist first, then work. The same receipt twice is one receipt.",
        [
            request(
                "Submit a clean receipt",
                "POST",
                "/receipts",
                body=office,
                headers={"Idempotency-Key": "{{run}}-office"},
                tests=[
                    status(202),
                    "const body = pm.response.json();",
                    'pm.test("accepted, revision 1, submitted", () => {',
                    '  pm.expect(body.outcome).to.eql("accepted");',
                    "  pm.expect(body.revision).to.eql(1);",
                    '  pm.expect(body.state).to.eql("submitted");',
                    "});",
                ],
            ),
            request(
                "Repeat it with the same key",
                "POST",
                "/receipts",
                body=office,
                headers={"Idempotency-Key": "{{run}}-office"},
                tests=[
                    status(200),
                    'pm.test("existing, no second receipt", () => {',
                    '  pm.expect(pm.response.json().outcome).to.eql("existing");',
                    "  pm.expect(pm.response.json().revision).to.eql(1);",
                    "});",
                ],
            ),
            request(
                "Repeat it without a key",
                "POST",
                "/receipts",
                body=office,
                tests=[
                    status(200),
                    'pm.test("same content is the same receipt", () =>',
                    '  pm.expect(pm.response.json().outcome).to.eql("existing"));',
                ],
            ),
            request(
                "Reuse the key with another body",
                "POST",
                "/receipts",
                body=office_changed,
                headers={"Idempotency-Key": "{{run}}-office"},
                tests=[status(422), error_code("idempotency_key_reuse")],
            ),
            request(
                "Submit an invalid receipt",
                "POST",
                "/receipts",
                body={"receipt_id": "PM-{{run}}-BAD"},
                tests=[
                    status(422),
                    error_code("invalid_receipt"),
                    'pm.test("names the missing fields", () =>',
                    '  pm.expect(pm.response.json().error.details.fields).to.include("employee_id"));',
                ],
            ),
            request(
                "Submit a receipt that carries answer keys",
                "POST",
                "/receipts",
                body=with_answers,
                tests=[status(202)],
                description="The body has invented labels and notes. They are discarded.",
            ),
            request(
                "Read it back: the answer keys are gone",
                "GET",
                "/receipts/" + rid("FIREWALL"),
                tests=[
                    status(200),
                    "const text = pm.response.text();",
                    'pm.test("no labels, no notes, no expected exceptions", () => {',
                    '  pm.expect(text).to.not.include("labels");',
                    '  pm.expect(text).to.not.include("notes");',
                    '  pm.expect(text).to.not.include("invented answer key");',
                    "});",
                ],
            ),
            wait(
                "Wait for the clean receipt to be processed",
                "/receipts/" + rid("OFFICE"),
                f"{RESTING}.includes(body.state)",
                [
                    'pm.test("auto-approved with one evaluation", () => {',
                    '  pm.expect(body.state).to.eql("auto_approved");',
                    "  pm.expect(body.evaluation_version).to.eql(1);",
                    '  pm.expect(body.disposition).to.eql("pass");',
                    '  pm.expect(body.allowed_actions).to.eql(["reject"]);',
                    "});",
                    'pm.test("the result is what the batch run produces", () => {',
                    "  pm.expect(body.result.receipt_id).to.eql(body.receipt_id);",
                    '  pm.expect(body.result.run.model_id).to.be.a("string");',
                    "});",
                ],
            ),
            request(
                "Read the event trail",
                "GET",
                "/receipts/" + rid("OFFICE") + "/events",
                tests=[
                    status(200),
                    "const types = pm.response.json().items.map(e => e.type);",
                    'pm.test("submitted, classified, evaluated", () =>',
                    '  pm.expect(types).to.eql(["ReceiptSubmitted", "ReceiptClassified", "ReceiptEvaluated"]));',
                ],
            ),
        ],
    )

    revisions = folder(
        "2 Revisions",
        "The same receipt with different content is a new revision; the old one stays.",
        [
            request(
                "Submit the same receipt with another amount",
                "POST",
                "/receipts",
                body=office_changed,
                tests=[
                    status(202),
                    'pm.test("a new revision", () => {',
                    '  pm.expect(pm.response.json().outcome).to.eql("revision");',
                    "  pm.expect(pm.response.json().revision).to.eql(2);",
                    "});",
                ],
            ),
            request(
                "Revision 1 is superseded and still readable",
                "GET",
                "/receipts/" + rid("OFFICE") + "/revisions/1",
                tests=[
                    status(200),
                    'pm.test("superseded, with its evaluation", () => {',
                    '  pm.expect(pm.response.json().status).to.eql("superseded");',
                    "  pm.expect(pm.response.json().evaluations.length).to.eql(1);",
                    "});",
                ],
            ),
            wait(
                "Wait for revision 2",
                "/receipts/" + rid("OFFICE"),
                f"body.revision === 2 && {RESTING}.includes(body.state)",
                [
                    'pm.test("revision 2 is current and evaluated from scratch", () => {',
                    "  pm.expect(body.revision).to.eql(2);",
                    "  pm.expect(body.evaluation_version).to.eql(1);",
                    "});",
                ],
            ),
            request(
                "The trail records the superseded revision",
                "GET",
                "/receipts/" + rid("OFFICE") + "/events",
                tests=[
                    status(200),
                    "const types = pm.response.json().items.map(e => e.type);",
                    'pm.test("RevisionSuperseded is in the trail", () =>',
                    '  pm.expect(types).to.include("RevisionSuperseded"));',
                ],
            ),
        ],
    )

    batches = folder(
        "3 Batches",
        "Partial success is normal: bad rows are reported, the others proceed.",
        [
            request(
                "Submit a batch with a bad row",
                "POST",
                "/batches",
                raw=batch_text,
                content_type="application/x-ndjson",
                tests=[
                    status(207),
                    "const body = pm.response.json();",
                    'pm.collectionVariables.set("batchId", body.batch_id);',
                    'pm.test("row 2 is invalid and named, the others are accepted", () => {',
                    "  pm.expect(body.items.map(i => i.outcome)).to.eql(",
                    '    ["accepted", "invalid", "accepted"]);',
                    "  pm.expect(body.items[1].row).to.eql(2);",
                    '  pm.expect(body.items[1].error).to.include("not valid JSON");',
                    "});",
                ],
            ),
            request(
                "Submit the same batch again",
                "POST",
                "/batches",
                raw=batch_text,
                content_type="application/x-ndjson",
                tests=[
                    status(207),
                    'pm.test("every good row already exists, no new work", () =>',
                    "  pm.expect(pm.response.json().items.map(i => i.outcome)).to.eql(",
                    '    ["existing", "invalid", "existing"]));',
                ],
            ),
            wait(
                "Wait for the batch to be processed",
                "/batches/{{batchId}}",
                '!("submitted" in body.counts) && !("classifying" in body.counts)',
                [
                    'pm.test("two receipts at rest and one invalid row", () => {',
                    "  pm.expect(body.total).to.eql(3);",
                    "  pm.expect(body.counts.invalid).to.eql(1);",
                    "  pm.expect(body.counts.auto_approved).to.eql(2);",
                    "});",
                ],
            ),
            request(
                "List the receipts of the batch",
                "GET",
                "/receipts",
                query={"batch_id": "{{batchId}}"},
                tests=[
                    status(200),
                    'pm.test("two receipts", () => pm.expect(pm.response.json().total).to.eql(2));',
                ],
            ),
        ],
    )

    cascade = folder(
        "4 Cross-receipt re-evaluation",
        "Two meals for one employee-day break the daily cap only together (40 + 50 > 75, MEAL-01)."
        " The first receipt is evaluated again when the second lands.",
        [
            request(
                "Submit meal A (40.00)",
                "POST",
                "/receipts",
                body=meal_a,
                tests=[status(202)],
            ),
            wait(
                "Wait for meal A alone",
                "/receipts/" + rid("MEAL-A"),
                f"{RESTING}.includes(body.state)",
                [
                    'pm.test("A alone passes", () => {',
                    '  pm.expect(body.state).to.eql("auto_approved");',
                    "  pm.expect(" + rules() + ').to.not.include("MEAL-01");',
                    "});",
                ],
            ),
            request(
                "Submit meal B (50.00, same employee and day)",
                "POST",
                "/receipts",
                body=meal_b,
                tests=[status(202)],
            ),
            wait(
                "Wait for A to be evaluated again",
                "/receipts/" + rid("MEAL-A"),
                "body.evaluation_version === 2 && " + RESTING + ".includes(body.state)",
                [
                    'pm.collectionVariables.set("aEval", body.evaluation_version);',
                    'pm.test("MEAL-01 now appears on A, which returns to the queue with a notice", () => {',
                    '  pm.expect(body.state).to.eql("in_review");',
                    '  pm.expect(body.disposition).to.eql("flag");',
                    "  pm.expect(" + rules() + ').to.include("MEAL-01");',
                    '  pm.expect(body.notice).to.include("re-evaluation");',
                    "});",
                ],
            ),
            wait(
                "Wait for B",
                "/receipts/" + rid("MEAL-B"),
                f"{RESTING}.includes(body.state)",
                [
                    'pm.collectionVariables.set("bEval", body.evaluation_version);',
                    'pm.test("MEAL-01 appears on B too, as in the batch run", () => {',
                    "  pm.expect(" + rules() + ').to.include("MEAL-01");',
                    "  pm.expect(body.evaluation_version).to.eql(1);",
                    "});",
                ],
            ),
            request(
                "A's trail shows the notice",
                "GET",
                "/receipts/" + rid("MEAL-A") + "/events",
                tests=[
                    status(200),
                    "const types = pm.response.json().items.map(e => e.type);",
                    'pm.test("evaluated twice and a notice raised", () => {',
                    '  pm.expect(types.filter(t => t === "ReceiptEvaluated").length).to.eql(2);',
                    '  pm.expect(types).to.include("NoticeRaised");',
                    "});",
                ],
            ),
        ],
    )

    review = folder(
        "5 Reviewer actions on the flagged pair",
        "Meals A and B (employee E1) are flagged together. Approve or reject, correct a category. "
        "Every action is an event and an auditor_agreement score.",
        [
            act(
                "Approve a flagged receipt without a reason is refused",
                "MEAL-A",
                "approve",
                {"evaluation_version": "{{aEval}}"},
                [status(422), error_code("reason_required")],
            ),
            act(
                "A stale evaluation version is refused",
                "MEAL-A",
                "reject",
                {"evaluation_version": 99},
                [
                    status(409),
                    error_code("stale_evaluation"),
                    'pm.test("says which version is current", () =>',
                    "  pm.expect(pm.response.json().error.details.current_evaluation_version)"
                    '.to.eql(Number(pm.collectionVariables.get("aEval"))));',
                ],
            ),
            act(
                "Correct a category: the engine runs again",
                "MEAL-A",
                "correct-category",
                {
                    "evaluation_version": "{{aEval}}",
                    "line_id": rid("MEAL-A") + "-L1",
                    "category": "lodging",
                },
                [
                    status(200),
                    "const body = pm.response.json();",
                    'const before = Number(pm.collectionVariables.get("aEval"));',
                    'pm.test("new evaluation version with the human category", () => {',
                    "  pm.expect(body.evaluation_version).to.eql(before + 1);",
                    '  pm.expect(body.result.line_items[0].category).to.eql("lodging");',
                    "  pm.expect(body.result.line_items[0].confidence).to.eql(1);",
                    "  pm.expect("
                    + rules("body.result.exceptions")
                    + ').to.not.include("MEAL-01");',
                    "  pm.expect(body.agreement).to.eql(0);",
                    "  pm.expect(body.notice).to.eql(null);",
                    "});",
                ],
            ),
            request(
                "The correction made the line a dev-set candidate",
                "GET",
                "/receipts/" + rid("MEAL-A") + "/events",
                tests=[
                    status(200),
                    "const types = pm.response.json().items.map(e => e.type);",
                    'pm.test("corrected and marked", () => {',
                    '  pm.expect(types).to.include("LineCategoryCorrected");',
                    '  pm.expect(types).to.include("DevCandidateMarked");',
                    "});",
                ],
            ),
            wait(
                "Wait for B to be evaluated again after the correction",
                "/receipts/" + rid("MEAL-B"),
                "body.evaluation_version === 2",
                [
                    'pm.test("B lost MEAL-01 and, untouched, follows the new proposal silently", () => {',
                    "  pm.expect(" + rules() + ').to.not.include("MEAL-01");',
                    '  pm.expect(body.state).to.eql("auto_approved");',
                    "  pm.expect(body.notice).to.eql(null);",
                    "});",
                ],
                "The correction queued B's re-evaluation, because A and B share an employee-day.",
            ),
            request(
                "Approve is not allowed on an auto-approved receipt",
                "POST",
                "/receipts/" + rid("OFFICE") + "/actions/approve",
                body={"actor": "alice", "evaluation_version": 1},
                tests=[
                    status(409),
                    error_code("action_not_allowed"),
                    'pm.test("lists what is allowed", () =>',
                    '  pm.expect(pm.response.json().error.details.allowed).to.eql(["reject"]));',
                ],
            ),
            request(
                "Rejecting it overrides the engine: a reason is required",
                "POST",
                "/receipts/" + rid("OFFICE") + "/actions/reject",
                body={"actor": "alice", "evaluation_version": 1},
                tests=[status(422), error_code("reason_required")],
            ),
            request(
                "Reject it with a reason code",
                "POST",
                "/receipts/" + rid("OFFICE") + "/actions/reject",
                body={
                    "actor": "alice",
                    "evaluation_version": 1,
                    "reason_code": "engine_missed_issue",
                    "note": "the merchant is not an approved vendor",
                },
                tests=[
                    status(200),
                    'pm.test("rejected, and the override is counted as disagreement", () => {',
                    '  pm.expect(pm.response.json().state).to.eql("rejected");',
                    "  pm.expect(pm.response.json().agreement).to.eql(0);",
                    "  pm.expect(pm.response.json().allowed_actions).to.eql([]);",
                    "});",
                ],
            ),
        ],
    )

    routing = folder(
        "6 Escalation, information requests, and a decision that comes back",
        "Meals C and D (employee E2) are flagged together. C is escalated, D is asked for "
        "information. D's answer resolves the finding, and C, already acted on, returns to review.",
        [
            request(
                "Submit meals C and D as a batch",
                "POST",
                "/batches",
                raw="\n".join([json.dumps(meal_c), json.dumps(meal_d)]),
                content_type="application/x-ndjson",
                tests=[status(202)],
            ),
            wait(
                "Wait for D",
                "/receipts/" + rid("MEAL-D"),
                f"{RESTING}.includes(body.state)",
                [
                    'pm.collectionVariables.set("dEval", body.evaluation_version);',
                    'pm.test("D is in review with MEAL-01", () => {',
                    '  pm.expect(body.state).to.eql("in_review");',
                    "  pm.expect(" + rules() + ').to.include("MEAL-01");',
                    "});",
                ],
            ),
            wait(
                "Wait for C",
                "/receipts/" + rid("MEAL-C"),
                f"{RESTING}.includes(body.state)",
                ['pm.collectionVariables.set("cEval", body.evaluation_version);'],
            ),
            act(
                "Escalate C to Compliance",
                "MEAL-C",
                "escalate",
                {"evaluation_version": "{{cEval}}", "reason": "possible split bill"},
                [
                    status(200),
                    'pm.test("with Compliance, in agreement with the engine", () => {',
                    '  pm.expect(pm.response.json().state).to.eql("compliance");',
                    "  pm.expect(pm.response.json().agreement).to.eql(1);",
                    "});",
                ],
            ),
            act(
                "Escalating again is not allowed",
                "MEAL-C",
                "escalate",
                {"evaluation_version": "{{cEval}}", "reason": "again"},
                [status(409), error_code("action_not_allowed")],
            ),
            act(
                "Request information about D",
                "MEAL-D",
                "request-info",
                {"evaluation_version": "{{dEval}}", "question": "Who attended?"},
                [
                    status(200),
                    'pm.test("waiting for the employee", () =>',
                    '  pm.expect(pm.response.json().state).to.eql("needs_info"));',
                ],
            ),
            request(
                "The employee answers: a new revision of D",
                "POST",
                "/receipts",
                body=meal_d_answer,
                tests=[
                    status(202),
                    'pm.test("revision 2, back to the start", () => {',
                    '  pm.expect(pm.response.json().outcome).to.eql("revision");',
                    '  pm.expect(pm.response.json().state).to.eql("submitted");',
                    "});",
                ],
            ),
            wait(
                "Wait for D's answer to be evaluated",
                "/receipts/" + rid("MEAL-D"),
                "body.revision === 2 && " + RESTING + ".includes(body.state)",
                [
                    'pm.test("two attendees: the daily total is within the cap", () => {',
                    "  pm.expect(" + rules() + ').to.not.include("MEAL-01");',
                    "});",
                ],
            ),
            wait(
                "Wait for C to be evaluated again",
                "/receipts/" + rid("MEAL-C"),
                "body.evaluation_version === 2",
                [
                    'pm.collectionVariables.set("cEval", body.evaluation_version);',
                    'pm.test("C acted on, so it returns to review with a notice", () => {',
                    '  pm.expect(body.state).to.eql("in_review");',
                    '  pm.expect(body.notice).to.include("after your decision");',
                    "  pm.expect(" + rules() + ').to.not.include("MEAL-01");',
                    "});",
                ],
            ),
            act(
                "Approve C: it now passes, so no reason is needed",
                "MEAL-C",
                "approve",
                {"evaluation_version": "{{cEval}}"},
                [
                    status(200),
                    'pm.test("approved in agreement, the notice is cleared", () => {',
                    '  pm.expect(pm.response.json().state).to.eql("approved");',
                    "  pm.expect(pm.response.json().agreement).to.eql(1);",
                    "  pm.expect(pm.response.json().notice).to.eql(null);",
                    "});",
                ],
            ),
        ],
    )

    compliance = folder(
        "7 Critical findings and unknowns",
        "A critical finding goes straight to Compliance.",
        [
            request(
                "Submit two gifts to a government official",
                "POST",
                "/batches",
                raw="\n".join([json.dumps(gift), json.dumps(gift_2)]),
                content_type="application/x-ndjson",
                tests=[status(202)],
            ),
            wait(
                "Wait for the first gift",
                "/receipts/" + rid("GIFT"),
                f"{RESTING}.includes(body.state)",
                [
                    'pm.collectionVariables.set("gEval", body.evaluation_version);',
                    'pm.test("GIFT-04 is critical, so the receipt is with Compliance", () => {',
                    '  pm.expect(body.state).to.eql("compliance");',
                    "  pm.expect(" + rules() + ').to.include("GIFT-04");',
                    '  pm.expect(body.allowed_actions).to.not.include("escalate");',
                    "});",
                ],
            ),
            wait(
                "Wait for the second gift",
                "/receipts/" + rid("GIFT-2"),
                f"{RESTING}.includes(body.state)",
                ['pm.collectionVariables.set("g2Eval", body.evaluation_version);'],
            ),
            act(
                "Approving the flagged gift needs a reason",
                "GIFT",
                "approve",
                {"evaluation_version": "{{gEval}}"},
                [status(422), error_code("reason_required")],
            ),
            act(
                "Compliance approves it with a reason code",
                "GIFT",
                "approve",
                {"evaluation_version": "{{gEval}}", "reason_code": "policy_exception_granted"},
                [
                    status(200),
                    'pm.test("approved, an override of the engine", () => {',
                    '  pm.expect(pm.response.json().state).to.eql("approved");',
                    "  pm.expect(pm.response.json().agreement).to.eql(0);",
                    "});",
                ],
            ),
            act(
                "Compliance rejects the second gift",
                "GIFT-2",
                "reject",
                {"evaluation_version": "{{g2Eval}}", "note": "anti-corruption policy"},
                [
                    status(200),
                    'pm.test("rejected, in agreement", () => {',
                    '  pm.expect(pm.response.json().state).to.eql("rejected");',
                    "  pm.expect(pm.response.json().agreement).to.eql(1);",
                    "});",
                ],
            ),
            request(
                "Retry a receipt that did not fail",
                "POST",
                "/receipts/" + rid("GIFT") + "/retry",
                tests=[status(409), error_code("action_not_allowed")],
            ),
            request(
                "Unknown receipt",
                "GET",
                "/receipts/PM-{{run}}-DOES-NOT-EXIST",
                tests=[status(404), error_code("not_found")],
            ),
            request(
                "List what is still waiting for a person",
                "GET",
                "/receipts",
                query={"state": "in_review", "limit": "5"},
                tests=[
                    status(200),
                    'pm.test("a list with a total", () =>',
                    '  pm.expect(pm.response.json().total).to.be.a("number"));',
                ],
            ),
        ],
    )

    health = folder(
        "0 Setup",
        "The server must run with a worker: `uv run epv serve --with-worker --offline --no-trace`.",
        [
            request(
                "Health",
                "GET",
                "/health",
                tests=[
                    status(200),
                    'pm.test("ok", () => pm.expect(pm.response.json().status).to.eql("ok"));',
                ],
            )
        ],
    )

    return {
        "info": {
            "name": "Expense Policy Validator: backend (iteration 3)",
            "description": (
                "Every endpoint and the edge cases of specs/004-backend-lifecycle. Start the API "
                "with a worker: `uv run epv serve --with-worker --offline --no-trace`, import this "
                "collection and the environment, and run the collection in order."
            ),
            "schema": SCHEMA,
        },
        "variable": [{"key": "baseUrl", "value": "http://localhost:8000"}],
        "event": [
            {
                "listen": "prerequest",
                "script": script(
                    [
                        "// One id per run, so the receipts of a run never join an earlier one.",
                        'if (!pm.collectionVariables.get("run")) {',
                        '  pm.collectionVariables.set("run", Date.now().toString(36));',
                        "}",
                    ]
                ),
            }
        ],
        "item": [health, intake, revisions, batches, cascade, review, routing, compliance],
    }


def environment() -> dict[str, Any]:
    return {
        "id": "7d6c4c3e-3a52-4b7e-9a39-4f1c1c3b5d01",
        "name": "EPV local",
        "values": [{"key": "baseUrl", "value": "http://localhost:8000", "enabled": True}],
        "_postman_variable_scope": "environment",
    }


def main() -> None:
    (HERE / "epv.postman_collection.json").write_text(
        json.dumps(build(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (HERE / "epv.local.postman_environment.json").write_text(
        json.dumps(environment(), indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
