from datetime import date
from decimal import Decimal

from octopus_compare.config import Config
from octopus_compare.pipeline import run_comparison
from tests.fixtures.api_samples import (
    ACCOUNT, PRODUCTS_LIST, PRODUCT_DETAIL,
    FLEX_ELEC_RATES, FLEX_ELEC_STANDING,
)


class FakeClient:
    """Routes paths to canned payloads covering one flat-rate month."""

    def get(self, path, params=None):
        if path == "accounts/A-8F18337C/":
            return ACCOUNT
        if path == "electricity-meter-points/1200033187430/":
            return {"gsp": "_C"}
        if path == "products/SILVER-26-06-01/":
            return PRODUCT_DETAIL
        raise AssertionError(path)

    def get_results(self, path, params=None):
        if path == "products/":
            return PRODUCTS_LIST["results"]
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
