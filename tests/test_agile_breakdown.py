from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from octopus_compare.agile_breakdown import (
    _period_rates, compute_decomposition, compute_hours, HourBucket, compute_breakdown, AgileBreakdown)
from octopus_compare.costing import SupplyCost

UTC = ZoneInfo("UTC")


def test_decomposition_algebra_and_pounds():
    period_rates = {
        datetime(2026, 3, 1, 0, 0, tzinfo=UTC): Decimal("10"),
        datetime(2026, 3, 1, 0, 30, tzinfo=UTC): Decimal("20"),
        datetime(2026, 3, 1, 1, 0, tzinfo=UTC): Decimal("20"),
        datetime(2026, 3, 1, 1, 30, tzinfo=UTC): Decimal("30"),
    }  # mean = 20
    energy_delta = Decimal("2.00")
    d = compute_decomposition(period_rates, Decimal("24.0"), Decimal("22.0"), Decimal("100"),
                              energy_delta_pounds=energy_delta)
    assert d.time_avg_p == Decimal("20.0")
    assert d.structural_p == Decimal("4.0")      # 24.0 - 20.0  (Agile cheaper on avg)
    assert d.behavioural_p == Decimal("-2.0")    # 20.0 - 22.0  (you use at dearer times)
    assert d.total_p == Decimal("2.0")           # 24.0 - 22.0
    assert d.structural_p + d.behavioural_p == d.total_p
    assert d.structural_pounds == Decimal("4.00")     # 4.0 * 100 / 100
    assert d.behavioural_pounds == Decimal("-2.00")
    assert d.total_pounds == energy_delta          # ties to the cost-engine delta
    assert d.total_kwh == Decimal("100")


def test_decomposition_inverse_agile_dearer():
    period_rates = {datetime(2026, 3, 1, 0, 0, tzinfo=UTC): Decimal("28")}
    energy_delta = Decimal("-6.00")
    d = compute_decomposition(period_rates, Decimal("24.0"), Decimal("30.0"), Decimal("100"),
                              energy_delta_pounds=energy_delta)
    assert d.time_avg_p == Decimal("28.0")
    assert d.structural_p == Decimal("-4.0")     # Agile DEARER on average
    assert d.behavioural_p == Decimal("-2.0")
    assert d.total_p == Decimal("-6.0")          # Agile dearer overall
    assert d.total_pounds == energy_delta


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
                          Decimal("1"), date(2026, 3, 1), date(2026, 3, 1),
                          energy_delta_pounds=Decimal("0.04"))
    assert isinstance(b, AgileBreakdown)
    assert len(b.by_hour) == 24
    assert b.decomposition.time_avg_p == Decimal("20.0")   # 99 excluded by the filter
    assert b.decomposition.structural_p + b.decomposition.behavioural_p == b.decomposition.total_p


def test_pound_components_reconcile_exactly():
    # structural=0.5p and behavioural=0.5p each round to £0.01 independently;
    # the old non-residual code summed to £0.02 ≠ total £0.01. The residual
    # derivation (behavioural = total - structural) keeps the sum exact.
    # total_pounds must equal the energy_delta_pounds passed from the cost engine.
    rates = {datetime(2026, 1, 1, tzinfo=UTC): Decimal("19.5")}
    energy_delta = Decimal("0.01")
    d = compute_decomposition(rates, Decimal("20"), Decimal("19"), Decimal("1"),
                              energy_delta_pounds=energy_delta)
    assert d.structural_pounds + d.behavioural_pounds == d.total_pounds
    assert d.total_pounds == energy_delta


def test_reconciliation_energy_plus_standing_plus_vat_equals_total():
    # Regression test for the honesty bug: the report printed
    #   Energy £X + Standing £Y + VAT £Z = Total £T  where X+Y+Z != T
    # because the energy £ was computed from quantized p/kWh * kWh (different base
    # from the cost engine's total).  After the fix, total_pounds == the cost
    # engine's true energy delta so the equation always balances.
    #
    # flex: energy=£200, standing=£30, vat=£11.50, total=£241.50
    # agile: energy=£180, standing=£35, vat=£10.75, total=£225.75
    flex = SupplyCost(
        consumption_kwh=Decimal("1000"),
        energy_pounds=Decimal("200.00"),
        standing_pounds=Decimal("30.00"),
        subtotal_pounds=Decimal("230.00"),
        vat_pounds=Decimal("11.50"),
        total_pounds=Decimal("241.50"),
    )
    agile = SupplyCost(
        consumption_kwh=Decimal("1000"),
        energy_pounds=Decimal("180.00"),
        standing_pounds=Decimal("35.00"),
        subtotal_pounds=Decimal("215.00"),
        vat_pounds=Decimal("10.75"),
        total_pounds=Decimal("225.75"),
    )

    # Component deltas (flex - agile)
    energy_delta = flex.energy_pounds - agile.energy_pounds      # £20.00
    standing_delta = flex.standing_pounds - agile.standing_pounds  # -£5.00
    vat_delta = flex.vat_pounds - agile.vat_pounds               # £0.75
    total_delta = flex.total_pounds - agile.total_pounds          # £15.75

    # The fundamental invariant that the report reconciliation relies on:
    assert energy_delta + standing_delta + vat_delta == total_delta

    # Build a decomposition with total_pounds == energy_delta (the fix).
    rates = {datetime(2026, 1, 1, tzinfo=UTC): Decimal("20")}
    d = compute_decomposition(rates, Decimal("24"), Decimal("22"), Decimal("1000"),
                              energy_delta_pounds=energy_delta)
    assert d.total_pounds == energy_delta
    assert d.structural_pounds + d.behavioural_pounds == d.total_pounds

    # Simulate what _agile_decomposition_lines sums for the reconciliation line:
    # energy_delta + standing_delta + vat_delta == total_delta
    assert d.total_pounds + standing_delta + vat_delta == total_delta
