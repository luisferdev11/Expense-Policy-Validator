"""PERS-01..03, HOUSE-01, HEALTH-01, LAUNDRY-01 (T054, FR-014, A4, A5, A6)."""

from tests.factories import classified, cls, item, receipt
from tests.unit.rule_helpers import engine, exc, ids, one


def test_pers_01_and_02_medium_and_pa_is_not_a_baggage_reference() -> None:
    f = one(["personal_care", "clothing"], pre_approval_ref="PA-2026-0003")
    assert exc(f, "PERS-01").severity == "medium"
    assert exc(f, "PERS-02").severity == "medium"
    assert exc(f, "PERS-01").line_ids == ["SYN-1-L1"]
    assert exc(f, "PERS-02").line_ids == ["SYN-1-L2"]


def test_pers_03_tobacco_high_and_house_01_medium() -> None:
    f = one(["tobacco", "household_goods"])
    assert exc(f, "PERS-03").severity == "high"
    assert exc(f, "HOUSE-01").severity == "medium"


def test_laundry_01_short_trip_or_no_trip_is_low() -> None:
    assert (
        exc(one(["laundry_service"], trip_id="T1", trip_nights=3), "LAUNDRY-01").severity == "low"
    )
    assert exc(one(["laundry_service"]), "LAUNDRY-01").severity == "low"
    assert "LAUNDRY-01" not in ids(one(["laundry_service"], trip_id="T1", trip_nights=4))


def test_health_01_otc_without_a_trip_is_low() -> None:
    f = one(["health_otc"])
    assert exc(f, "HEALTH-01").severity == "low"
    assert exc(f, "HEALTH-01").line_ids == ["SYN-1-L1"]


def test_health_01_prescription_is_medium_with_its_own_evidence() -> None:
    f = one([cls("SYN-1-L1", "other", subtype="prescription_medication")], trip_id="T1")
    finding = exc(f, "HEALTH-01")
    assert finding.severity == "medium"
    assert finding.evidence.startswith("Prescription medication is never reimbursable")


def test_health_01_a4_trip_total_raises_on_every_receipt_with_its_own_lines() -> None:
    a = classified(
        receipt([item(1, receipt_id="SYN-A", amount="15.00")], receipt_id="SYN-A", trip_id="T9"),
        "health_otc",
    )
    b = classified(
        receipt(
            [item(1, receipt_id="SYN-B", amount="11.00"), item(2, receipt_id="SYN-B")],
            receipt_id="SYN-B",
            trip_id="T9",
        ),
        "health_otc",
        "office_supplies",
    )
    from tests.engine_cases.helpers import run

    fa, fb = run(a, batch=[a, b]), run(b, batch=[a, b])
    assert exc(fa, "HEALTH-01").line_ids == ["SYN-A-L1"]
    assert exc(fb, "HEALTH-01").line_ids == ["SYN-B-L1"]


def test_health_01_trip_total_of_exactly_25_raises_nothing() -> None:
    f = engine([item(1, amount="25.00")], ["health_otc"], trip_id="T2")
    assert "HEALTH-01" not in ids(f)
