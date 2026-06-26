import json
from datetime import date
from decimal import Decimal

from octopus_compare.costing import SupplyCost
from octopus_compare.tracker import TrackerVersion, FixedProduct
from octopus_compare.report import (
    ComparisonResult, MonthlyRow, recommend, format_text, format_json)


def _cost(total):
    t = Decimal(total)
    return SupplyCost(Decimal("800"), t, Decimal("0"), t, Decimal("0"), t)


def _result(flex, trk, fix):
    return ComparisonResult(
        period_from=date(2026, 1, 1), period_to=date(2026, 5, 31),
        region="C",
        tracker=TrackerVersion("SILVER-26-04-01", "Octopus Tracker April 2026 v1",
                               date(2026, 4, 1), None),
        fixed=FixedProduct("OE-FIX-12M-26-06-24", "Octopus 12M Fixed June 2026 v5",
                           date(2026, 6, 24)),
        elec_flexible=_cost(flex), elec_tracker=_cost(trk), elec_fixed=_cost(fix),
        gas_flexible=_cost("0"), gas_tracker=_cost("0"), gas_fixed=_cost("0"),
        monthly=[
            MonthlyRow(date(2026, 1, 1), 31, Decimal("210.40"), Decimal("194.00"), Decimal("205.10")),
            MonthlyRow(date(2026, 4, 1), 30, Decimal("158.40"), Decimal("135.10"), Decimal("152.30")),
        ],
    )


def test_totals_and_cheapest():
    r = _result("877.39", "783.83", "855.10")
    assert r.flexible_total == Decimal("877.39")
    assert r.tracker_total == Decimal("783.83")
    assert r.fixed_total == Decimal("855.10")
    assert r.cheapest == "tracker"


def test_monthly_row_cheapest_and_tiebreak():
    row = MonthlyRow(date(2026, 1, 1), 31, Decimal("194.00"), Decimal("194.00"), Decimal("205.10"))
    assert row.cheapest == "flexible"  # tie flexible vs tracker -> flexible wins
    row2 = MonthlyRow(date(2026, 1, 1), 31, Decimal("210.40"), Decimal("194.00"), Decimal("205.10"))
    assert row2.cheapest == "tracker"


def test_recommend_variants():
    assert recommend(_result("877.39", "783.83", "855.10")) == "SWITCH"   # tracker 10.7% < flex
    assert recommend(_result("783.83", "877.39", "855.10")) == "STAY"     # flexible cheapest
    assert recommend(_result("100.00", "99.00", "101.00")) == "MARGINAL"  # tracker only 1% under


def test_format_text_three_columns_and_marker():
    text = format_text(_result("877.39", "783.83", "855.10"))
    assert "Flexible" in text and "Tracker" in text and "Fixed" in text
    assert "SILVER-26-04-01" in text
    assert "OE-FIX-12M-26-06-24" in text
    assert "12M Fixed" in text
    assert "Region C" in text
    assert "✓" in text
    assert "Jan 2026" in text and "Apr 2026" in text
    assert "Cheapest over this period: TRACKER" in text


def test_format_json_structure():
    data = json.loads(format_json(_result("877.39", "783.83", "855.10")))
    assert data["region"] == "C"
    assert data["tracker"]["product_code"] == "SILVER-26-04-01"
    assert data["fixed"]["product_code"] == "OE-FIX-12M-26-06-24"
    assert data["flexible_total"] == "877.39"
    assert data["tracker_total"] == "783.83"
    assert data["fixed_total"] == "855.10"
    assert data["cheapest"] == "tracker"
    assert data["recommendation"] == "SWITCH"
    assert data["electricity"]["fixed"]["total"] == "855.10"
    assert len(data["monthly"]) == 2
    assert data["monthly"][0]["fixed"] == "205.10"
    assert data["monthly"][0]["cheapest"] == "tracker"
