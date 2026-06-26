import json
from datetime import date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

from octopus_compare.agile import AgileVersion
from octopus_compare.agile_breakdown import AgileBreakdown, Decomposition, HourBucket
from octopus_compare.agile_insight import AgileInsight, HalfHourStat
from octopus_compare.costing import SupplyCost
from octopus_compare.report import (
    AgileResult, AgileMonthlyRow, recommend_agile,
    format_agile_text, format_agile_json, _agile_decomposition_lines)

_LONDON = ZoneInfo("Europe/London")


def _cost(total):
    t = Decimal(total)
    return SupplyCost(Decimal("100"), t, Decimal("0"), t, Decimal("0"), t)


def _insight():
    when = datetime(2026, 3, 1, 13, 30, tzinfo=_LONDON)
    stat = HalfHourStat(when, Decimal("-2.0"), Decimal("0.4"), Decimal("-0.01"))
    return AgileInsight(
        agile_effective_p=Decimal("18.4"), flex_effective_p=Decimal("24.5"),
        peak_window=(time(16, 0), time(19, 0)),
        peak_kwh=Decimal("250"), offpeak_kwh=Decimal("562"),
        peak_pct=Decimal("31.0"), peak_agile_pounds=Decimal("58.20"),
        peak_flex_pounds=Decimal("61.70"), cheapest=stat, priciest=stat,
        negative_count=37)


def _breakdown(structural="7.1", behavioural="-1.3", total="5.8"):
    decomp = Decomposition(
        flex_p=Decimal("24.0"), time_avg_p=Decimal("16.9"), load_p=Decimal("18.2"),
        structural_p=Decimal(structural), behavioural_p=Decimal(behavioural),
        total_p=Decimal(total),
        structural_pounds=Decimal("43.85"), behavioural_pounds=Decimal("-7.89"),
        total_pounds=Decimal("35.95"), total_kwh=Decimal("622"))
    hours = [HourBucket(h, Decimal("4.0"), Decimal("15.0"), None) for h in range(24)]
    hours[14] = HourBucket(14, Decimal("4.8"), Decimal("10.2"), "cheap")
    hours[18] = HourBucket(18, Decimal("9.4"), Decimal("32.5"), "dear")
    return AgileBreakdown(decomp, hours, Decimal("29.0"), Decimal("41.0"))


def _result(flex_total, agile_total):
    v = AgileVersion("AGILE-24-10-01", "Agile Octopus", date(2024, 10, 1), None)
    return AgileResult(
        period_from=date(2026, 1, 1), period_to=date(2026, 5, 31), region="C",
        agile_versions=[v],
        elec_flexible=_cost(flex_total), elec_agile=_cost(agile_total),
        monthly=[AgileMonthlyRow(date(2026, 1, 1), 31,
                                 Decimal(flex_total), Decimal(agile_total))],
        insight=_insight(),
        breakdown=_breakdown())


def test_recommend_agile_switch():
    assert recommend_agile(_result("286.80", "234.64")) == "SWITCH"


def test_recommend_agile_stay():
    assert recommend_agile(_result("234.64", "286.80")) == "STAY"


def test_recommend_agile_marginal():
    # Agile saves ~2.0% vs Flexible -> MARGINAL (boundary: saving_pct <= 2).
    assert recommend_agile(_result("240.00", "235.21")) == "MARGINAL"


def test_format_agile_text_has_columns_and_insight():
    text = format_agile_text(_result("286.80", "234.64"))
    assert "Agile Comparison" in text and "(electricity only)" in text
    assert "AGILE-24-10-01" in text
    assert "Flexible" in text and "Agile" in text and "✓" in text
    assert "Time-of-use insight" in text
    assert "18.4p/kWh" in text
    assert "AGILE — £234.64" in text


def test_format_agile_json_shape():
    data = json.loads(format_agile_json(_result("286.80", "234.64")))
    assert data["cheapest"] == "agile"
    assert data["agile_total"] == "234.64"
    assert data["electricity"]["agile"]["total"] == "234.64"
    assert data["insight"]["agile_effective_p"] == "18.4"
    assert data["recommendation"] == "SWITCH"
    assert data["agile_versions"][0]["product_code"] == "AGILE-24-10-01"


def test_format_agile_text_has_decomposition_cheaper():
    text = format_agile_text(_result("286.80", "234.64"))
    assert "Why Agile is cheaper" in text
    assert "Agile if you used power evenly" in text
    assert "Structural (Agile cheaper on average)" in text
    assert "Energy subtotal" in text
    assert "-£7.89" in text                 # minus before the £
    assert "Hour-of-day (London)" in text
    assert "Usage in 6 cheapest hours: 29.0%" in text


def test_format_agile_text_decomposition_inverse():
    res = _result("234.64", "286.80")       # Agile dearer overall
    res.breakdown = _breakdown(structural="-4.0", behavioural="-2.0", total="-6.0")
    text = format_agile_text(res)
    assert "Why Agile is more expensive" in text
    assert "Agile dearer on average" in text
    assert "you use at dearer times" in text
    assert "Energy subtotal" in text


def test_format_agile_json_has_breakdown():
    data = json.loads(format_agile_json(_result("286.80", "234.64")))
    assert data["breakdown"]["decomposition"]["structural_p"] == "7.1"
    assert data["breakdown"]["decomposition"]["total_pounds"] == "35.95"
    assert len(data["breakdown"]["by_hour"]) == 24
    assert data["breakdown"]["by_hour"][18]["marker"] == "dear"
    assert data["breakdown"]["cheapest6_usage_pct"] == "29.0"


def _decomp(total_p):
    return Decomposition(
        flex_p=Decimal("25"), time_avg_p=Decimal("22"), load_p=Decimal("20"),
        structural_p=Decimal("3"), behavioural_p=Decimal("2"), total_p=total_p,
        structural_pounds=Decimal("30"), behavioural_pounds=Decimal("20"),
        total_pounds=Decimal("50"), total_kwh=Decimal("1000"))


def test_header_follows_total_bill_not_energy():
    # energy favours Agile (total_p>0) but the bill total favours Flexible
    lines = _agile_decomposition_lines(
        _decomp(Decimal("5")), total_delta_pounds=Decimal("-2.50"),
        standing_delta_pounds=Decimal("-7.40"), vat_delta_pounds=Decimal("-0.25"))
    assert any("more expensive" in line for line in lines)
    assert any("Energy-only price pattern" in line for line in lines)
    assert any("=" in line and "Total" in line for line in lines)  # reconciliation
