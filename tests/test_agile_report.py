import json
from datetime import date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

from octopus_compare.agile import AgileVersion
from octopus_compare.agile_breakdown import AgileBreakdown, Decomposition, HourBucket
from octopus_compare.agile_insight import AgileInsight, HalfHourStat
from octopus_compare.costing import SupplyCost
from octopus_compare.coverage import AgileCoverage
from octopus_compare.report import (
    AgileResult, AgileMonthlyRow, recommend_agile, agile_verdict_suppressed,
    format_agile_text, format_agile_json, _agile_decomposition_lines)
from octopus_compare.verdict import Verdict

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


def _complete_cov():
    return AgileCoverage(30, 30, [], Decimal("100"), Decimal("100"),
                         Decimal("0"), [])


def _result(flex_total, agile_total, cov=None, allow_partial=False):
    v = AgileVersion("AGILE-24-10-01", "Agile Octopus", date(2024, 10, 1), None)
    if cov is None:
        cov = _complete_cov()
    return AgileResult(
        period_from=date(2026, 1, 1), period_to=date(2026, 5, 31), region="C",
        agile_versions=[v],
        elec_flexible=_cost(flex_total), elec_agile=_cost(agile_total),
        monthly=[AgileMonthlyRow(date(2026, 1, 1), 31,
                                 Decimal(flex_total), Decimal(agile_total))],
        insight=_insight(),
        breakdown=_breakdown(),
        coverage=cov,
        allow_partial=allow_partial)


# ---- helpers for new suppression tests ----

def _sc(total, kwh="100"):
    return SupplyCost(Decimal(kwh), Decimal("0"), Decimal("0"), Decimal("0"),
                      Decimal("0"), Decimal(total))


def _agile_cov(complete=True):
    if complete:
        return AgileCoverage(30, 30, [], Decimal("100"), Decimal("100"),
                             Decimal("0"), [])
    return AgileCoverage(30, 15, [date(2026, 1, 5)], Decimal("100"),
                         Decimal("50"), Decimal("50.0"),
                         ["half-hourly total (50 kWh) differs from daily total (100 kWh) by 50.0%"])


def _agile_result(flex, agile, cov):
    # minimal stub: insight/breakdown not exercised by these tests
    return AgileResult(
        period_from=date(2026, 1, 1), period_to=date(2026, 2, 1), region="C",
        agile_versions=[], elec_flexible=_sc(flex), elec_agile=_sc(agile),
        monthly=[], insight=None, breakdown=None, coverage=cov,
        allow_partial=False)


def test_agile_verdict_suppressed_on_partial():
    assert agile_verdict_suppressed(_agile_result("100", "90", _agile_cov(False))) is True


def test_agile_recommend_uses_tie_band():
    assert recommend_agile(_agile_result("1000", "900", _agile_cov())) == Verdict.SWITCH
    # flex=812 vs agile=820: flex is cheaper by £8 (~0.99%) — inside the 2% band → TOO_CLOSE
    assert recommend_agile(_agile_result("812", "820", _agile_cov())) == Verdict.TOO_CLOSE


def test_recommend_agile_switch():
    assert recommend_agile(_result("286.80", "234.64")) == Verdict.SWITCH


def test_recommend_agile_stay():
    assert recommend_agile(_result("234.64", "286.80")) == Verdict.STAY


def test_recommend_agile_marginal():
    # Agile saves ~2.0% vs Flexible -> TOO_CLOSE (within 2% band)
    assert recommend_agile(_result("240.00", "235.21")) == Verdict.TOO_CLOSE


def test_format_agile_text_has_columns_and_insight():
    text = format_agile_text(_result("286.80", "234.64"))
    assert "Agile Comparison" in text and "(electricity only)" in text
    assert "AGILE-24-10-01" in text
    assert "Flexible" in text and "Agile" in text and "✓" in text
    assert "Time-of-use insight" in text
    assert "18.4p/kWh" in text
    assert "SWITCH to Agile" in text


def test_format_agile_text_shows_flex_consumption():
    text = format_agile_text(_result("286.80", "234.64"))
    # Both flex and agile consumption should be shown
    assert "100 kWh" in text
    # The consumption line should show both
    assert "consumption" in text


def test_format_agile_text_has_coverage():
    text = format_agile_text(_result("286.80", "234.64"))
    assert "Coverage:" in text


def test_format_agile_text_suppresses_verdict_on_partial():
    partial_cov = _agile_cov(False)
    text = format_agile_text(_result("286.80", "234.64", cov=partial_cov))
    assert "NO RECOMMENDATION" in text
    assert "SWITCH" not in text


def test_format_agile_text_suppresses_ticks_on_partial():
    partial_cov = _agile_cov(False)
    text = format_agile_text(_result("286.80", "234.64", cov=partial_cov))
    assert "✓" not in text


def test_format_agile_text_shows_ticks_when_complete():
    text = format_agile_text(_result("286.80", "234.64"))
    assert "✓" in text


def test_format_agile_json_shape():
    data = json.loads(format_agile_json(_result("286.80", "234.64")))
    assert data["agile_total"] == "234.64"
    assert data["electricity"]["agile"]["total"] == "234.64"
    assert data["insight"]["agile_effective_p"] == "18.4"
    assert data["recommendation"] == "SWITCH"
    assert data["agile_versions"][0]["product_code"] == "AGILE-24-10-01"


def test_format_agile_json_has_verdict_suppressed():
    data = json.loads(format_agile_json(_result("286.80", "234.64")))
    assert "verdict_suppressed" in data
    assert data["verdict_suppressed"] is False


def test_format_agile_json_has_coverage():
    data = json.loads(format_agile_json(_result("286.80", "234.64")))
    assert "coverage" in data
    c = data["coverage"]
    assert c["daily_days"] == 30
    assert c["hh_days"] == 30
    assert c["missing_hh_days"] == []
    assert "daily_kwh" in c
    assert "hh_kwh" in c
    assert "divergence_pct" in c
    assert "notes" in c


def test_format_agile_json_suppressed_on_partial():
    partial_cov = _agile_cov(False)
    data = json.loads(format_agile_json(_result("286.80", "234.64", cov=partial_cov)))
    assert data["verdict_suppressed"] is True
    assert data["recommendation"] is None


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


# ---- Fix 2: AgileMonthlyRow.verdict uses tie band ----

def test_agile_monthly_row_verdict_too_close():
    """A month within the tie band must report TOO_CLOSE, not a winner."""
    row = AgileMonthlyRow(date(2026, 1, 1), 31, Decimal("100.40"), Decimal("100.00"))
    assert row.verdict == Verdict.TOO_CLOSE


def test_agile_monthly_row_verdict_stay():
    """Flexible clearly cheaper → STAY."""
    row = AgileMonthlyRow(date(2026, 1, 1), 31, Decimal("80.00"), Decimal("100.00"))
    assert row.verdict == Verdict.STAY


def test_agile_monthly_row_verdict_switch():
    """Agile clearly cheaper → SWITCH."""
    row = AgileMonthlyRow(date(2026, 1, 1), 31, Decimal("100.00"), Decimal("80.00"))
    assert row.verdict == Verdict.SWITCH


def test_format_agile_text_no_tick_for_too_close_month():
    """A month within the tie band must render with no ✓ in the monthly table."""
    base = _result("286.80", "234.64")
    # Replace monthly with a single row that's within tie band
    base.monthly = [AgileMonthlyRow(date(2026, 1, 1), 31, Decimal("100.40"), Decimal("100.00"))]
    text = format_agile_text(base)
    monthly_section = text.split("By month")[1].split("Total")[0]
    assert "✓" not in monthly_section


def test_format_agile_text_tick_for_clear_switch_month():
    """A month with a clear Agile win must show ✓ on the Agile column."""
    base = _result("286.80", "234.64")
    base.monthly = [AgileMonthlyRow(date(2026, 1, 1), 31, Decimal("100.00"), Decimal("80.00"))]
    text = format_agile_text(base)
    monthly_section = text.split("By month")[1].split("Total")[0]
    assert "✓" in monthly_section


# ---- Fix 1 (agile): JSON monthly verdict key and suppression ----

def test_format_agile_json_monthly_verdict_suppressed_when_incomplete():
    """Monthly verdicts must be None in JSON when coverage is incomplete."""
    partial_cov = _agile_cov(False)
    base = _result("286.80", "234.64", cov=partial_cov)
    data = json.loads(format_agile_json(base))
    assert data["verdict_suppressed"] is True
    assert data["monthly"][0]["verdict"] is None


def test_format_agile_json_monthly_verdict_present_when_clean():
    """Monthly verdict key is emitted and equals the row's verdict when clean."""
    data = json.loads(format_agile_json(_result("286.80", "234.64")))
    assert data["verdict_suppressed"] is False
    # The single monthly row has flex=286.80, agile=234.64 → SWITCH
    assert data["monthly"][0]["verdict"] == Verdict.SWITCH.value


def test_format_agile_json_monthly_has_no_cheapest_key():
    """The old 'cheapest' key must no longer appear in monthly rows."""
    data = json.loads(format_agile_json(_result("286.80", "234.64")))
    assert "cheapest" not in data["monthly"][0]
