from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from octopus_compare.agile_breakdown import (
    _period_rates, compute_decomposition, compute_hours, HourBucket, compute_breakdown, AgileBreakdown)

UTC = ZoneInfo("UTC")


def test_decomposition_algebra_and_pounds():
    period_rates = {
        datetime(2026, 3, 1, 0, 0, tzinfo=UTC): Decimal("10"),
        datetime(2026, 3, 1, 0, 30, tzinfo=UTC): Decimal("20"),
        datetime(2026, 3, 1, 1, 0, tzinfo=UTC): Decimal("20"),
        datetime(2026, 3, 1, 1, 30, tzinfo=UTC): Decimal("30"),
    }  # mean = 20
    d = compute_decomposition(period_rates, Decimal("24.0"), Decimal("22.0"), Decimal("100"))
    assert d.time_avg_p == Decimal("20.0")
    assert d.structural_p == Decimal("4.0")      # 24.0 - 20.0  (Agile cheaper on avg)
    assert d.behavioural_p == Decimal("-2.0")    # 20.0 - 22.0  (you use at dearer times)
    assert d.total_p == Decimal("2.0")           # 24.0 - 22.0
    assert d.structural_p + d.behavioural_p == d.total_p
    assert d.structural_pounds == Decimal("4.00")     # 4.0 * 100 / 100
    assert d.behavioural_pounds == Decimal("-2.00")
    assert d.total_pounds == Decimal("2.00")
    assert d.total_kwh == Decimal("100")


def test_decomposition_inverse_agile_dearer():
    period_rates = {datetime(2026, 3, 1, 0, 0, tzinfo=UTC): Decimal("28")}
    d = compute_decomposition(period_rates, Decimal("24.0"), Decimal("30.0"), Decimal("100"))
    assert d.time_avg_p == Decimal("28.0")
    assert d.structural_p == Decimal("-4.0")     # Agile DEARER on average
    assert d.behavioural_p == Decimal("-2.0")
    assert d.total_p == Decimal("-6.0")          # Agile dearer overall
    assert d.total_pounds == Decimal("-6.00")


def test_period_filter_excludes_boundary_day():
    rate_map = {
        datetime(2026, 5, 28, 0, 0, tzinfo=UTC): Decimal("10"),
        datetime(2026, 5, 30, 0, 0, tzinfo=UTC): Decimal("12"),   # == period_to, kept
        datetime(2026, 5, 31, 0, 0, tzinfo=UTC): Decimal("99"),   # +1 day, dropped
    }
    pr = _period_rates(rate_map, date(2026, 5, 28), date(2026, 5, 30))
    assert datetime(2026, 5, 30, 0, 0, tzinfo=UTC) in pr
    assert datetime(2026, 5, 31, 0, 0, tzinfo=UTC) not in pr
    assert len(pr) == 2


def test_compute_hours_buckets_and_markers():
    hh = {datetime(2026, 3, 1, 14, 0, tzinfo=UTC): Decimal("1"),
          datetime(2026, 3, 1, 18, 0, tzinfo=UTC): Decimal("1")}
    period_rates = {datetime(2026, 3, 1, 14, 0, tzinfo=UTC): Decimal("5"),
                    datetime(2026, 3, 1, 18, 0, tzinfo=UTC): Decimal("40")}
    buckets, _c, _d = compute_hours(hh, period_rates, Decimal("2"), Decimal("22.5"))
    assert len(buckets) == 24
    assert buckets[14].usage_pct == Decimal("50.0")
    assert buckets[14].avg_price_p == Decimal("5.0")
    assert buckets[14].marker == "cheap"        # 5 < 22.5*0.8 = 18
    assert buckets[18].marker == "dear"         # 40 > 22.5*1.3 = 29.25
    assert buckets[0].avg_price_p == Decimal("0")  # no slots that hour
    assert buckets[0].marker is None


def test_compute_hours_summary_shares():
    # hours 0..11 priced 1..12p; all usage in hour 11 (the dearest)
    period_rates = {datetime(2026, 3, 1, h, 0, tzinfo=UTC): Decimal(h + 1) for h in range(12)}
    hh = {datetime(2026, 3, 1, 11, 0, tzinfo=UTC): Decimal("1")}
    _b, cheap6, dear6 = compute_hours(hh, period_rates, Decimal("1"), Decimal("6.5"))
    assert dear6 == Decimal("100.0")     # hours 6..11 are the dearest 6; usage is in 11
    assert cheap6 == Decimal("0.0")      # hours 0..5 are the cheapest 6; no usage there


def test_compute_breakdown_integrates():
    rate_map = {
        datetime(2026, 3, 1, 0, 0, tzinfo=UTC): Decimal("20"),
        datetime(2026, 3, 2, 0, 0, tzinfo=UTC): Decimal("99"),  # +1 day, filtered out
    }
    hh = {datetime(2026, 3, 1, 0, 0, tzinfo=UTC): Decimal("1")}
    b = compute_breakdown(hh, rate_map, Decimal("24.0"), Decimal("20.0"),
                          Decimal("1"), date(2026, 3, 1), date(2026, 3, 1))
    assert isinstance(b, AgileBreakdown)
    assert len(b.by_hour) == 24
    assert b.decomposition.time_avg_p == Decimal("20.0")   # 99 excluded by the filter
    assert b.decomposition.structural_p + b.decomposition.behavioural_p == b.decomposition.total_p


def test_pound_components_reconcile_exactly():
    rates = {datetime(2026, 1, 1, h, tzinfo=UTC): Decimal("20") for h in range(5)}
    d = compute_decomposition(rates, Decimal("25.3"), Decimal("18.7"),
                              Decimal("1234.5"))
    assert d.structural_pounds + d.behavioural_pounds == d.total_pounds
