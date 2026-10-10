"""Engine settings come from docs/decisions/policy_decisions.yaml (T013, A1-A9)."""

from decimal import Decimal

from expense_validator.adapters.config_files import load_settings


def test_fx_defaults_follow_a1() -> None:
    s = load_settings()
    assert s.fx_date_basis == "transaction"
    assert s.fx_rate_kind == "recorded"
    assert s.fx_missing_rate_disposition == "review"


def test_exc03_threshold_is_the_value_chosen_on_dev() -> None:
    s = load_settings()
    assert (s.exc03_threshold, s.exc03_threshold_status) == (Decimal("0.95"), "chosen_on_dev")


def test_reference_prefixes_follow_a5() -> None:
    assert load_settings().reference_prefixes == {"PA-": "pre_approval"}


def test_all_decisions_are_present() -> None:
    assert load_settings().decision_ids == tuple(f"A{i}" for i in range(1, 10))


def test_home_currency_table_covers_the_dataset_countries() -> None:
    s = load_settings()
    for country, currency in {
        "US": "USD",
        "IN": "INR",
        "JP": "JPY",
        "SG": "SGD",
        "GB": "GBP",
        "DE": "EUR",
        "FR": "EUR",
        "NL": "EUR",
        "IE": "EUR",
        "PT": "EUR",
        "ES": "EUR",
    }.items():
        assert s.home_currency[country] == currency
