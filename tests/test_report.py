import json
from datetime import date
from decimal import Decimal

from octopus_compare.costing import SupplyCost
from octopus_compare.tracker import TrackerVersion
from octopus_compare.report import (
    ComparisonResult, MonthlyRow, recommend, format_text, format_json)


def _cost(consumption, energy, standing, vat, total):
    d = Decimal
    return SupplyCost(d(consumption), d(energy), d(standing),
                      d(energy) + d(standing), d(vat), d(total))


def _result(flex_total, trk_total):
    f = _cost("800", flex_total, "0", "0", flex_total)
    t = _cost("800", trk_total, "0", "0", trk_total)
    zero = _cost("0", "0", "0", "0", "0")
    return ComparisonResult(
        period_from=date(2026, 1, 1), period_to=date(2026, 5, 31),
        region="C",
        tracker=TrackerVersion("SILVER-26-04-01", "Octopus Tracker April 2026 v1",
                               date(2026, 4, 1), None),
        elec_flexible=f, elec_tracker=t, gas_flexible=zero, gas_tracker=zero,
        monthly=[
            MonthlyRow(date(2026, 1, 1), 31, Decimal("210.40"), Decimal("194.00")),
            MonthlyRow(date(2026, 4, 1), 30, Decimal("158.40"), Decimal("135.10")),
        ],
    )


def test_totals_delta_and_pct():
    r = _result("877.39", "783.83")
    assert r.flexible_total == Decimal("877.39")
    assert r.tracker_total == Decimal("783.83")
    assert r.delta == Decimal("-93.56")
    assert r.pct == Decimal("-10.7")


def test_monthly_row_delta():
    row = MonthlyRow(date(2026, 1, 1), 31, Decimal("210.40"), Decimal("194.00"))
    assert row.delta == Decimal("-16.40")


def test_recommend_variants():
    assert recommend(_result("877.39", "783.83")) == "SWITCH BACK"
    assert recommend(_result("783.83", "877.39")) == "STAY"
    assert recommend(_result("100.00", "101.00")) == "MARGINAL"


def test_format_text_has_columns_blocks_and_tracker():
    text = format_text(_result("877.39", "783.83"))
    assert "Flexible" in text and "Tracker" in text
    assert "SILVER-26-04-01" in text
    assert "Region C" in text
    assert "energy" in text and "standing" in text and "VAT" in text
    assert "Jan 2026" in text and "Apr 2026" in text
    assert "SWITCH BACK" in text


def test_format_json_structure():
    data = json.loads(format_json(_result("877.39", "783.83")))
    assert data["recommendation"] == "SWITCH BACK"
    assert data["region"] == "C"
    assert data["tracker"]["product_code"] == "SILVER-26-04-01"
    assert data["flexible_total"] == "877.39"
    assert data["tracker_total"] == "783.83"
    assert len(data["monthly"]) == 2
    assert data["monthly"][0]["flexible"] == "210.40"
    assert data["electricity"]["flexible"]["total"] == "877.39"
