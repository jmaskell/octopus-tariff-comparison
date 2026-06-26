from datetime import date
from decimal import Decimal

import pytest

from octopus_compare.rates import build_lookup, VersionedLookup, RateLookup, _Window, flat_lookup
from tests.fixtures.api_samples import TRACKER_ELEC_RATES, FLEX_ELEC_RATES


def test_tracker_rate_per_day():
    lookup = build_lookup(TRACKER_ELEC_RATES["results"])
    assert lookup.rate_for(date(2026, 3, 1)) == Decimal("18.78")
    assert lookup.rate_for(date(2026, 3, 2)) == Decimal("19.81")


def test_flexible_open_ended_rate():
    lookup = build_lookup(FLEX_ELEC_RATES["results"])
    assert lookup.rate_for(date(2026, 4, 15)) == Decimal("23.71")
    assert lookup.rate_for(date(2026, 12, 31)) == Decimal("23.71")


def test_missing_rate_raises():
    lookup = build_lookup(TRACKER_ELEC_RATES["results"])
    with pytest.raises(KeyError):
        lookup.rate_for(date(2026, 3, 10))


def _flat_lookup(value):
    return RateLookup([_Window(date.min, date.max, Decimal(value))])


def test_versioned_lookup_picks_by_date():
    sep = (date(2025, 9, 2), date(2026, 4, 1), _flat_lookup("18.00"))
    apr = (date(2026, 4, 1), None, _flat_lookup("20.00"))
    vl = VersionedLookup([apr, sep])  # unordered on purpose
    assert vl.rate_for(date(2026, 3, 15)) == Decimal("18.00")
    assert vl.rate_for(date(2026, 4, 15)) == Decimal("20.00")


def test_versioned_lookup_uncovered_raises():
    vl = VersionedLookup([(date(2026, 4, 1), None, _flat_lookup("20.00"))])
    with pytest.raises(KeyError):
        vl.rate_for(date(2026, 3, 1))


def test_flat_lookup_returns_value_for_any_day():
    lk = flat_lookup(Decimal("21.50"))
    assert lk.rate_for(date(2026, 1, 1)) == Decimal("21.50")
    assert lk.rate_for(date(2030, 12, 31)) == Decimal("21.50")
