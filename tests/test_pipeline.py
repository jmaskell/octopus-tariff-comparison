from datetime import date
from decimal import Decimal

from octopus_compare.config import Config
from octopus_compare.pipeline import run_comparison
from tests.fixtures.api_samples import (
    ACCOUNT, FLEX_ELEC_RATES, FLEX_ELEC_STANDING,
)


class FakeClient:
    """Routes paths to canned payloads covering one flat-rate month.

    The account (from the ACCOUNT fixture) has a SILVER (tracker) agreement and a
    VAR (flexible) agreement on each meter, so resolve_tracker walks newest-first:
    VAR product detail (is_tracker False) then SILVER product detail (True).
    """

    def get(self, path, params=None):
        if path == "accounts/A-8F18337C/":
            return ACCOUNT
        if path == "products/VAR-22-11-01/":
            return {"is_tracker": False}
        if path == "products/SILVER-24-12-31/":
            return {"is_tracker": True}
        raise AssertionError(path)

    def get_results(self, path, params=None):
        if "consumption" in path:
            return [{"consumption": 9.0,
                     "interval_start": "2026-04-01T00:00:00Z",
                     "interval_end": "2026-04-02T00:00:00Z"}]
        if "standard-unit-rates" in path:
            return FLEX_ELEC_RATES["results"]
        if "standing-charges" in path:
            return FLEX_ELEC_STANDING["results"]
        raise AssertionError(path)


def _config():
    return Config(
        api_key="sk", account="A-8F18337C",
        period_from=date(2026, 4, 1), period_to=date(2026, 4, 2),
        output_format="text", gas_calorific_value=Decimal("39.5"),
        gas_units="kwh", verbose=False,
    )


def test_run_comparison_produces_result():
    result = run_comparison(FakeClient(), _config())
    assert result.period_from == date(2026, 4, 1)
    assert result.actual_total > 0
    assert result.tracker_total > 0


def test_actual_resolvers_price_per_day_across_agreements():
    from octopus_compare.account import MeterPoint, Agreement
    from octopus_compare.pipeline import _actual_resolvers

    meter = MeterPoint("mpan", ["s"], [
        Agreement("E-1R-SILVER-24-12-31-C", date(2026, 3, 1), date(2026, 3, 24)),
        Agreement("E-1R-VAR-22-11-01-C", date(2026, 3, 24), None),
    ])

    class SplitRateClient:
        def get_results(self, path, params=None):
            if "standing-charges" in path:
                return [{"value_exc_vat": 40.0, "valid_from": None, "valid_to": None}]
            if "SILVER" in path:
                return [{"value_exc_vat": 30.0,
                         "valid_from": "2026-03-01T00:00:00Z",
                         "valid_to": "2026-03-24T00:00:00Z"}]
            return [{"value_exc_vat": 20.0,
                     "valid_from": "2026-03-24T00:00:00Z", "valid_to": None}]

    cfg = Config(
        api_key="x", account="A",
        period_from=date(2026, 3, 20), period_to=date(2026, 3, 28),
        output_format="text", gas_calorific_value=Decimal("39.5"),
        gas_units="kwh", verbose=False,
    )
    rate_for, _sc = _actual_resolvers(SplitRateClient(), "electricity", meter, cfg)
    assert rate_for(date(2026, 3, 23)) == Decimal("30")  # Tracker (SILVER) day
    assert rate_for(date(2026, 3, 24)) == Decimal("20")  # switch day -> Flexible
    assert rate_for(date(2026, 3, 27)) == Decimal("20")  # Flexible day
