import json
from datetime import date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

from octopus_compare.agile import AgileVersion
from octopus_compare.agile_insight import AgileInsight, HalfHourStat
from octopus_compare.costing import SupplyCost
from octopus_compare.report import (
    AgileResult, AgileMonthlyRow, recommend_agile,
    format_agile_text, format_agile_json)

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


def _result(flex_total, agile_total):
    v = AgileVersion("AGILE-24-10-01", "Agile Octopus", date(2024, 10, 1), None)
    return AgileResult(
        period_from=date(2026, 1, 1), period_to=date(2026, 5, 31), region="C",
        agile_versions=[v],
        elec_flexible=_cost(flex_total), elec_agile=_cost(agile_total),
        monthly=[AgileMonthlyRow(date(2026, 1, 1), 31,
                                 Decimal(flex_total), Decimal(agile_total))],
        insight=_insight())


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
