from datetime import date, time
from decimal import Decimal

import pytest

from octopus_compare.config import Config
from octopus_compare.agile_pipeline import run_agile_comparison
from octopus_compare.pipeline import PricingError
from tests.fixtures.api_samples import ACCOUNT_AGILE, AGILE_PRODUCTS_LIST


def _hh_rows(day, slots):
    # slots: list of (HH:MM, kwh)
    out = []
    for hhmm, kwh in slots:
        out.append({"consumption": kwh,
                    "interval_start": f"{day}T{hhmm}:00Z",
                    "interval_end": f"{day}T{hhmm}:00Z"})
    return out


def _rate_rows(day, slots):
    out = []
    for hhmm, value in slots:
        out.append({"value_exc_vat": value,
                    "valid_from": f"{day}T{hhmm}:00Z",
                    "valid_to": f"{day}T{hhmm}:00Z"})
    return out


HH = [("00:00", 1.0), ("16:00", 1.0)]           # 2 kWh on 2026-03-01
AGILE_RATES = [("00:00", -2.0), ("16:00", 30.0)]


class AgileFakeClient:
    """Flexible (VAR) flat at 24p/40p; Agile cheaper on average; one Agile
    version; half-hourly usage + rates for 2026-03-01."""

    def get(self, path, params=None):
        if path == "accounts/A-8F18337C/":
            return ACCOUNT_AGILE
        if path == "products/VAR-22-11-01/":
            return {"is_tracker": False}
        raise AssertionError(path)

    def get_results(self, path, params=None):
        if path == "products/":
            return AGILE_PRODUCTS_LIST
        if "consumption" in path:
            if params and params.get("group_by") == "day":
                return _hh_rows("2026-03-01", HH)   # daily call: same total kWh
            return _hh_rows("2026-03-01", HH)
        if "standing-charges" in path:
            value = 40.0 if "VAR" in path else 45.0
            return [{"value_exc_vat": value, "valid_from": None, "valid_to": None}]
        if "AGILE" in path:                          # half-hourly unit rates
            return _rate_rows("2026-03-01", AGILE_RATES)
        return [{"value_exc_vat": 24.0, "valid_from": None, "valid_to": None}]  # VAR unit


def _config(**kw):
    base = dict(
        api_key="sk", account="A-8F18337C",
        period_from=date(2026, 3, 1), period_to=date(2026, 3, 2),
        output_format="text", gas_calorific_value=Decimal("39.5"),
        gas_units="kwh", verbose=False, command="agile",
        agile_product=None, peak_window=(time(16, 0), time(19, 0)))
    base.update(kw)
    return Config(**base)


def test_run_agile_comparison_basic():
    result = run_agile_comparison(AgileFakeClient(), _config())
    assert result.region == "C"
    assert result.agile_versions[0].product_code == "AGILE-24-10-01"
    # Agile (avg 14p/kWh) cheaper than Flexible (24p/kWh) on equal usage.
    assert result.agile_total < result.flexible_total
    assert result.cheapest == "agile"
    assert result.elec_agile.consumption_kwh == Decimal("2.0")
    # insight populated
    assert result.insight.negative_count == 1
    assert result.insight.priciest.rate_p == Decimal("30.0")


def test_run_agile_flexible_baseline_matches_daily_engine():
    # Flexible total here is computed by the unmodified daily supply_cost:
    # energy round(2 kWh × 24p)=48p + standing 40p = 88p subtotal;
    # VAT round(88 × 0.05)=round(4.4)=4p; total 92p -> £0.92.
    result = run_agile_comparison(AgileFakeClient(), _config())
    assert result.elec_flexible.total_pounds == Decimal("0.92")


class NoHalfHourlyClient(AgileFakeClient):
    def get_results(self, path, params=None):
        if "consumption" in path:
            return []
        return super().get_results(path, params)


def test_run_agile_no_halfhourly_data_raises():
    with pytest.raises(PricingError):
        run_agile_comparison(NoHalfHourlyClient(), _config())
