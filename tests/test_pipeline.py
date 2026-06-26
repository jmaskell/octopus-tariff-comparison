import pytest
from datetime import date
from decimal import Decimal

from octopus_compare.config import Config
from octopus_compare.pipeline import run_comparison, PricingError
from octopus_compare.report import format_text
from tests.fixtures.api_samples import (
    ACCOUNT, ELEC_TWO_MONTH, GAS_TWO_MONTH, FIXED_PRODUCTS_LIST)


class FakeClient:
    """Tracker (SILVER, open-ended) cheapest; Fixed (OE-FIX-12M) between Tracker
    and Flexible; flat rates; two-month consumption."""

    UNIT = {"SILVER": {"electricity": 18.00, "gas": 5.00},
            "OE-FIX-12M": {"electricity": 20.00, "gas": 5.30},
            "VAR": {"electricity": 23.71, "gas": 5.63}}
    STAND = {"SILVER": {"electricity": 37.65, "gas": 28.52},
             "OE-FIX-12M": {"electricity": 38.00, "gas": 28.00},
             "VAR": {"electricity": 42.18, "gas": 28.06}}

    def get(self, path, params=None):
        if path == "accounts/A-8F18337C/":
            return ACCOUNT
        if path == "products/VAR-22-11-01/":
            return {"is_tracker": False}
        if path == "products/SILVER-24-12-31/":
            return {"code": "SILVER-24-12-31", "full_name": "Octopus Tracker Dec 2024",
                    "is_tracker": True,
                    "available_from": "2024-12-31T00:00:00Z", "available_to": None}
        raise AssertionError(path)

    def get_results(self, path, params=None):
        if path == "products/":
            return FIXED_PRODUCTS_LIST
        supply = "electricity" if "electricity" in path else "gas"
        if "consumption" in path:
            return ELEC_TWO_MONTH if supply == "electricity" else GAS_TWO_MONTH
        family = ("SILVER" if "SILVER" in path
                  else "OE-FIX-12M" if "OE-FIX-12M" in path else "VAR")
        table = self.STAND if "standing-charges" in path else self.UNIT
        return [{"value_exc_vat": table[family][supply], "valid_from": None, "valid_to": None}]


def _config():
    return Config(
        api_key="sk", account="A-8F18337C",
        period_from=date(2026, 3, 30), period_to=date(2026, 4, 2),
        output_format="text", gas_calorific_value=Decimal("39.5"),
        gas_units="kwh", verbose=False,
    )


def test_run_comparison_has_three_tariffs():
    result = run_comparison(FakeClient(), _config())
    assert result.region == "C"
    assert result.tracker.product_code == "SILVER-24-12-31"
    assert result.fixed.product_code == "OE-FIX-12M-26-06-24"
    # three independent totals; Tracker cheapest, Fixed between Tracker and Flexible
    assert result.tracker_total < result.fixed_total < result.flexible_total
    # tracker_versions list is populated
    assert len(result.tracker_versions) >= 1
    assert result.tracker_versions[0].product_code == "SILVER-24-12-31"
    # per-supply fixed totals sum to the grand fixed total
    assert result.elec_fixed.total_pounds + result.gas_fixed.total_pounds == result.fixed_total
    assert [r.month for r in result.monthly] == [date(2026, 3, 1), date(2026, 4, 1)]
    # coverage and gas_units are populated
    assert result.coverage.complete is True
    assert result.gas_units.resolved == "kwh"


def test_run_comparison_text_renders_fixed():
    text = format_text(run_comparison(FakeClient(), _config()))
    assert "OE-FIX-12M-26-06-24" in text
    # Fixed info appears in the FORWARD LOCK-IN CHECK section
    assert "FORWARD LOCK-IN CHECK" in text
    assert "12M Fixed" in text
    assert "Mar 2026" in text and "Apr 2026" in text


class FakeClientGappedFlex(FakeClient):
    """Same as FakeClient but the Flexible (VAR) rates start on 2026-04-01,
    leaving Mar 30/31 uncovered — should trigger PricingError."""

    def get_results(self, path, params=None):
        if path == "products/":
            return FIXED_PRODUCTS_LIST
        supply = "electricity" if "electricity" in path else "gas"
        if "consumption" in path:
            return ELEC_TWO_MONTH if supply == "electricity" else GAS_TWO_MONTH
        family = ("SILVER" if "SILVER" in path
                  else "OE-FIX-12M" if "OE-FIX-12M" in path else "VAR")
        table = self.STAND if "standing-charges" in path else self.UNIT
        # For VAR (Flexible) rates, start on Apr 1 so Mar days are uncovered.
        if family == "VAR":
            return [{"value_exc_vat": table[family][supply],
                     "valid_from": "2026-04-01T00:00:00Z", "valid_to": None}]
        return [{"value_exc_vat": table[family][supply], "valid_from": None, "valid_to": None}]


def test_uncovered_day_raises_pricing_error():
    with pytest.raises(PricingError):
        run_comparison(FakeClientGappedFlex(), _config())


def test_tracker_product_override_prices_whole_window():
    cfg = Config(
        api_key="sk", account="A-8F18337C",
        period_from=date(2026, 3, 30), period_to=date(2026, 4, 2),
        output_format="text", gas_calorific_value=Decimal("39.5"),
        gas_units="kwh", verbose=False,
        tracker_product="SILVER-24-12-31",
    )
    result = run_comparison(FakeClient(), cfg)
    assert result.tracker.product_code == "SILVER-24-12-31"
    assert len(result.monthly) == 2
