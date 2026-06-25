from decimal import Decimal

from octopus_compare.units import m3_to_kwh, DEFAULT_CALORIFIC_VALUE
from tests.fixtures import bills


def test_default_calorific_value():
    assert DEFAULT_CALORIFIC_VALUE == Decimal("39.5")


def test_m3_to_kwh_matches_bills():
    for m3, cv, expected in bills.GAS_CONVERSIONS:
        assert abs(m3_to_kwh(m3, cv) - expected) <= Decimal("0.5")
