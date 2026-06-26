from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from octopus_compare.agile_costing import agile_supply_cost

_UTC = ZoneInfo("UTC")


def _const(value):
    return lambda _key: Decimal(value)


def test_agile_supply_cost_basic():
    kwh = {
        datetime(2026, 3, 1, 0, 0, tzinfo=_UTC): Decimal("1.0"),
        datetime(2026, 3, 1, 0, 30, tzinfo=_UTC): Decimal("2.0"),
    }
    cost = agile_supply_cost(kwh, _const("20.0"), _const("45.0"))
    # energy = round(1*20 + 2*20) = 60p; standing = 45p (one day); subtotal 105p
    assert cost.energy_pounds == Decimal("0.60")
    assert cost.standing_pounds == Decimal("0.45")
    assert cost.vat_pounds == Decimal("0.05")        # round(105*0.05)=5p
    assert cost.total_pounds == Decimal("1.10")
    assert cost.consumption_kwh == Decimal("3.0")


def test_agile_supply_cost_handles_negative_rates():
    kwh = {datetime(2026, 3, 1, 13, 30, tzinfo=_UTC): Decimal("2.0")}

    def rate(_instant):
        return Decimal("-3.0")

    cost = agile_supply_cost(kwh, rate, _const("0.0"))
    # energy = round(2 * -3) = -6p -> a credit
    assert cost.energy_pounds == Decimal("-0.06")


def test_agile_supply_cost_rounds_per_day():
    # Two half-hours on different London days each round independently.
    kwh = {
        datetime(2026, 3, 1, 12, 0, tzinfo=_UTC): Decimal("0.333"),
        datetime(2026, 3, 2, 12, 0, tzinfo=_UTC): Decimal("0.333"),
    }
    cost = agile_supply_cost(kwh, _const("10.0"), _const("0.0"))
    # each day: round(0.333*10)=round(3.33)=3p -> 6p total
    assert cost.energy_pounds == Decimal("0.06")
