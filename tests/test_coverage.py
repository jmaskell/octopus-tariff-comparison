from datetime import date
from decimal import Decimal

from octopus_compare.coverage import (
    compare_coverage,
    agile_coverage,
)


def _days(y, m, d_start, d_end):
    return {date(y, m, d) for d in range(d_start, d_end + 1)}


def test_full_coverage_is_complete():
    elec = _days(2026, 1, 1, 31)
    gas = _days(2026, 1, 1, 31)
    cov = compare_coverage(date(2026, 1, 1), date(2026, 2, 1),
                           {"electricity": elec, "gas": gas})
    assert cov.complete
    assert all(s.priced_days == s.expected_days == 31 for s in cov.per_supply)


def test_trailing_unsettled_days_do_not_trip():
    # window asks to 31 Jan but both supplies only have data to the 28th
    elec = _days(2026, 1, 1, 28)
    gas = _days(2026, 1, 1, 28)
    cov = compare_coverage(date(2026, 1, 1), date(2026, 2, 1),
                           {"electricity": elec, "gas": gas})
    assert cov.complete  # expected trimmed to the 28th


def test_internal_gap_in_one_supply_flags_incomplete():
    elec = _days(2026, 1, 1, 31)
    gas = _days(2026, 1, 1, 31) - _days(2026, 1, 10, 15)  # 6-day hole
    cov = compare_coverage(date(2026, 1, 1), date(2026, 2, 1),
                           {"electricity": elec, "gas": gas})
    assert not cov.complete
    gas_cov = next(s for s in cov.per_supply if s.supply == "gas")
    assert gas_cov.priced_days == 25
    assert gas_cov.expected_days == 31
    assert date(2026, 1, 1) in gas_cov.missing_months


def test_cross_supply_span_mismatch_flags_gas():
    elec = _days(2026, 1, 1, 31)
    gas = _days(2026, 1, 16, 31)  # gas only second half
    cov = compare_coverage(date(2026, 1, 1), date(2026, 2, 1),
                           {"electricity": elec, "gas": gas})
    assert not cov.complete
    gas_cov = next(s for s in cov.per_supply if s.supply == "gas")
    assert gas_cov.priced_days == 16
    assert gas_cov.expected_days == 31


def test_no_data_at_all_has_note():
    cov = compare_coverage(date(2026, 1, 1), date(2026, 2, 1),
                           {"electricity": set(), "gas": set()})
    assert not cov.complete
    assert cov.notes


def test_agile_complete_when_hh_covers_daily():
    daily = _days(2026, 1, 1, 10)
    hh = _days(2026, 1, 1, 10)
    cov = agile_coverage(daily, hh, Decimal("100"), Decimal("100"))
    assert cov.complete


def test_agile_missing_hh_day_flags():
    daily = _days(2026, 1, 1, 10)
    hh = _days(2026, 1, 1, 10) - {date(2026, 1, 5)}
    cov = agile_coverage(daily, hh, Decimal("100"), Decimal("90"))
    assert not cov.complete
    assert date(2026, 1, 5) in cov.missing_hh_days


def test_agile_divergence_flags_even_with_all_days():
    daily = _days(2026, 1, 1, 10)
    hh = _days(2026, 1, 1, 10)
    cov = agile_coverage(daily, hh, Decimal("100"), Decimal("80"))  # 20% off
    assert not cov.complete
    assert cov.divergence_pct == Decimal("20.0")
    assert cov.notes
