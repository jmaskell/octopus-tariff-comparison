from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from octopus_compare.agile_breakdown import (
    _period_rates, compute_decomposition)

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
