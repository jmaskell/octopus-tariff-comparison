from datetime import date
from decimal import Decimal

import pytest

from octopus_compare.rates import build_lookup
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
