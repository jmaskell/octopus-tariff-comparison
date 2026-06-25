from datetime import date
from decimal import Decimal

import pytest

from octopus_compare.config import Config
from octopus_compare.pipeline import run_comparison, PricingError
from octopus_compare.report import format_text
from tests.fixtures.api_samples import ACCOUNT, ELEC_TWO_MONTH, GAS_TWO_MONTH


class FakeClient:
    """One Tracker version (SILVER-24-12-31, open-ended) and Flexible VAR-22-11-01,
    flat rates, two-month consumption. Tracker is cheaper than Flexible on both
    supplies, so the recommendation is SWITCH BACK."""

    UNIT = {"SILVER": {"electricity": 18.00, "gas": 5.00},
            "VAR": {"electricity": 23.71, "gas": 5.63}}
    STAND = {"SILVER": {"electricity": 37.65, "gas": 28.52},
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
        supply = "electricity" if "electricity" in path else "gas"
        if "consumption" in path:
            return ELEC_TWO_MONTH if supply == "electricity" else GAS_TWO_MONTH
        family = "SILVER" if "SILVER" in path else "VAR"
        table = self.STAND if "standing-charges" in path else self.UNIT
        return [{"value_exc_vat": table[family][supply], "valid_from": None, "valid_to": None}]


def _config():
    return Config(
        api_key="sk", account="A-8F18337C",
        period_from=date(2026, 3, 30), period_to=date(2026, 4, 2),
        output_format="text", gas_calorific_value=Decimal("39.5"),
        gas_units="kwh", verbose=False,
    )


def test_run_comparison_shape_and_aggregation():
    result = run_comparison(FakeClient(), _config())
    # region + latest tracker
    assert result.region == "C"
    assert result.tracker.product_code == "SILVER-24-12-31"
    # two calendar months (March, April)
    assert [row.month for row in result.monthly] == [date(2026, 3, 1), date(2026, 4, 1)]
    assert result.monthly[0].days == 2 and result.monthly[1].days == 1
    # monthly totals sum to the grand totals
    assert sum(r.flexible_pounds for r in result.monthly) == result.flexible_total
    assert sum(r.tracker_pounds for r in result.monthly) == result.tracker_total
    # per-supply totals sum to the grand totals
    assert (result.elec_flexible.total_pounds + result.gas_flexible.total_pounds
            == result.flexible_total)
    # Tracker is cheaper here
    assert result.tracker_total < result.flexible_total


class FakeClientUncoveredFlex(FakeClient):
    """Like FakeClient but FLEXIBLE rates only start from 2026-04-01,
    so a March window day has no covering rate."""

    def get_results(self, path, params=None):
        supply = "electricity" if "electricity" in path else "gas"
        if "consumption" in path:
            return ELEC_TWO_MONTH if supply == "electricity" else GAS_TWO_MONTH
        family = "SILVER" if "SILVER" in path else "VAR"
        table = self.STAND if "standing-charges" in path else self.UNIT
        if family == "VAR":
            # Flexible rates only valid from 2026-04-01 — will miss March days
            return [{"value_exc_vat": table[family][supply],
                     "valid_from": "2026-04-01T00:00:00Z", "valid_to": None}]
        return [{"value_exc_vat": table[family][supply], "valid_from": None, "valid_to": None}]


def test_uncovered_day_raises_pricing_error():
    cfg = _config()  # window is 2026-03-30 to 2026-04-02 (includes March days)
    with pytest.raises(PricingError) as exc_info:
        run_comparison(FakeClientUncoveredFlex(), cfg)
    assert "2026-03-30" in str(exc_info.value) or "Couldn't price" in str(exc_info.value)


class FakeClientTrackerOverride(FakeClient):
    """Override to SILVER-26-04-01 which has available_from=2026-04-01 (after window start).
    Single-version path must widen bounds to date.min/None to cover March days."""

    def get(self, path, params=None):
        if path == "accounts/A-8F18337C/":
            return ACCOUNT
        if path == "products/VAR-22-11-01/":
            return {"is_tracker": False}
        if path == "products/SILVER-26-04-01/":
            return {
                "code": "SILVER-26-04-01",
                "full_name": "Octopus Tracker April 2026 v1",
                "is_tracker": True,
                "available_from": "2026-04-01T00:00:00+01:00",
                "available_to": None,
            }
        raise AssertionError(path)

    def get_results(self, path, params=None):
        supply = "electricity" if "electricity" in path else "gas"
        if "consumption" in path:
            return ELEC_TWO_MONTH if supply == "electricity" else GAS_TWO_MONTH
        # All rates open-ended, covering all days
        table = self.STAND if "standing-charges" in path else self.UNIT
        family = "SILVER" if "SILVER" in path else "VAR"
        return [{"value_exc_vat": table[family][supply], "valid_from": None, "valid_to": None}]


def test_tracker_product_override_prices_whole_window():
    cfg = Config(
        api_key="sk", account="A-8F18337C",
        period_from=date(2026, 3, 30), period_to=date(2026, 4, 2),
        output_format="text", gas_calorific_value=Decimal("39.5"),
        gas_units="kwh", verbose=False,
        tracker_product="SILVER-26-04-01",
    )
    result = run_comparison(FakeClientTrackerOverride(), cfg)
    assert result.tracker.product_code == "SILVER-26-04-01"
    assert len(result.monthly) == 2


def test_run_comparison_text_renders():
    text = format_text(run_comparison(FakeClient(), _config()))
    assert "SILVER-24-12-31" in text
    assert "Mar 2026" in text and "Apr 2026" in text
    assert "SWITCH BACK" in text
