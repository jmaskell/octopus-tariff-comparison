import json
from datetime import date
from decimal import Decimal

from octopus_compare.coverage import Coverage, SupplyCoverage
from octopus_compare.consumption import GasUnitInfo
from octopus_compare.costing import SupplyCost
from octopus_compare.report import (
    ComparisonResult, MonthlyRow, recommend, fixed_verdict,
    verdict_suppressed, format_text,
)
from octopus_compare.tracker import TrackerVersion, FixedProduct
from octopus_compare.verdict import Verdict


def _sc(total, energy="0", standing="0", vat="0", kwh="0"):
    return SupplyCost(
        consumption_kwh=Decimal(kwh), energy_pounds=Decimal(energy),
        standing_pounds=Decimal(standing), subtotal_pounds=Decimal("0"),
        vat_pounds=Decimal(vat), total_pounds=Decimal(total))


def _complete_coverage():
    return Coverage([SupplyCoverage("electricity", 90, 90, []),
                     SupplyCoverage("gas", 90, 90, [])], [])


def _result(flex_total, trk_total, fix_total, coverage=None, gas_units=None,
            allow_partial=False):
    tv = TrackerVersion("SILVER-26-01-01", "Tracker Jan", date(2026, 1, 1), None)
    fp = FixedProduct("OE-FIX-12M-26-06-24", "12M Fixed", date(2026, 6, 24))
    return ComparisonResult(
        period_from=date(2026, 1, 1), period_to=date(2026, 4, 1), region="C",
        tracker=tv, tracker_versions=[tv], fixed=fp,
        elec_flexible=_sc(flex_total), elec_tracker=_sc(trk_total),
        elec_fixed=_sc(fix_total),
        gas_flexible=_sc("0"), gas_tracker=_sc("0"), gas_fixed=_sc("0"),
        monthly=[], coverage=coverage or _complete_coverage(),
        gas_units=gas_units or GasUnitInfo("m3", "m3", True, Decimal("11.36")),
        allow_partial=allow_partial)


def test_recommend_is_flexible_vs_tracker_only():
    # Tracker far cheaper than Flexible, Fixed irrelevant to the backtest verdict
    assert recommend(_result("1000", "900", "500")) == Verdict.SWITCH
    assert recommend(_result("900", "1000", "500")) == Verdict.STAY
    assert recommend(_result("812", "820", "100")) == Verdict.TOO_CLOSE


def test_fixed_verdict_is_fixed_vs_flexible():
    assert fixed_verdict(_result("1000", "999", "900")) == Verdict.SWITCH


def test_verdict_suppressed_on_incomplete_coverage():
    cov = Coverage([SupplyCoverage("electricity", 90, 90, []),
                    SupplyCoverage("gas", 60, 90, [date(2026, 2, 1)])], [])
    assert verdict_suppressed(_result("1000", "900", "800", coverage=cov)) is True


def test_verdict_suppressed_on_ambiguous_gas():
    gi = GasUnitInfo("auto", "m3", False, Decimal("11.36"))
    assert verdict_suppressed(_result("1000", "900", "800", gas_units=gi)) is True


def test_allow_partial_unsuppresses():
    cov = Coverage([SupplyCoverage("electricity", 90, 90, []),
                    SupplyCoverage("gas", 60, 90, [date(2026, 2, 1)])], [])
    assert verdict_suppressed(
        _result("1000", "900", "800", coverage=cov, allow_partial=True)) is False


def test_format_text_has_two_sections_and_no_recommendation_banner():
    cov = Coverage([SupplyCoverage("electricity", 90, 90, []),
                    SupplyCoverage("gas", 60, 90, [date(2026, 2, 1)])], [])
    out = format_text(_result("1000", "900", "800", coverage=cov))
    assert "HISTORICAL BACKTEST" in out
    assert "FORWARD LOCK-IN CHECK" in out
    assert "NO RECOMMENDATION" in out
    assert "Coverage:" in out
    assert "Gas units:" in out


def test_format_text_shows_backtest_verdict_when_clean():
    out = format_text(_result("1000", "900", "1100"))
    assert "SWITCH" in out
    assert "NO RECOMMENDATION" not in out


def test_monthly_row_verdict_too_close_has_no_tick():
    out = format_text(ComparisonResultWithMonth())
    # the close month (£100.00 vs £100.40) must not be ticked
    assert "✓" not in out.split("By month")[1].split("Total")[0]


def ComparisonResultWithMonth():
    base = _result("100.40", "100.00", "200")
    base.monthly = [MonthlyRow(date(2026, 1, 1), 31,
                               Decimal("100.40"), Decimal("100.00"))]
    return base
