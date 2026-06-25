from decimal import Decimal

from octopus_compare.costing import daily_energy_pence
from tests.fixtures import bills


def test_tracker_elec_energy_penny_exact():
    kwh = bills.elec_daily_kwh()
    rate = bills.elec_daily_rate()
    assert daily_energy_pence(kwh, lambda d: rate[d]) == bills.TRACKER_ELEC_ENERGY_P


def test_tracker_gas_energy_penny_exact():
    kwh = bills.gas_daily_kwh()
    rate = bills.gas_daily_rate()
    assert daily_energy_pence(kwh, lambda d: rate[d]) == bills.TRACKER_GAS_ENERGY_P


from octopus_compare.costing import standing_pence, supply_cost
from datetime import date


def test_tracker_elec_standing_charge():
    days = sorted(bills.elec_daily_kwh())
    sc = standing_pence(days, lambda d: bills.TRACKER_ELEC_SC_RATE)
    assert sc == bills.TRACKER_ELEC_SC_P  # £8.66


def test_tracker_elec_full_total_penny_exact():
    kwh = bills.elec_daily_kwh()
    rate = bills.elec_daily_rate()
    cost = supply_cost(kwh, lambda d: rate[d], lambda d: bills.TRACKER_ELEC_SC_RATE)
    assert cost.total_pounds == bills.TRACKER_ELEC_TOTAL_P / 100  # £55.88


def test_tracker_gas_full_total_penny_exact():
    kwh = bills.gas_daily_kwh()
    rate = bills.gas_daily_rate()
    cost = supply_cost(kwh, lambda d: rate[d], lambda d: bills.TRACKER_GAS_SC_RATE)
    assert cost.total_pounds == bills.TRACKER_GAS_TOTAL_P / 100  # £67.67


def test_flexible_references_within_tolerance():
    # Flexible bills print only monthly totals, so per-day rounding can't be
    # reproduced exactly; assert within 5p of the printed total.
    from decimal import Decimal
    for label, kwh, rate, sc_rate, ndays, energy, total in bills.FLEXIBLE_REFERENCES:
        days = [date(2026, 5, 1 + i) for i in range(ndays)]
        # All days present so standing charge spans the full period;
        # energy is a single bucket (only days[0] has non-zero kWh).
        daily = {d: (kwh if d == days[0] else Decimal(0)) for d in days}
        cost = supply_cost(daily, lambda d: rate, lambda d: sc_rate)
        assert abs(cost.total_pounds - total) <= Decimal("0.05"), label


from octopus_compare.costing import sum_supply_costs, SupplyCost
from decimal import Decimal as D


def test_sum_supply_costs_adds_components():
    a = SupplyCost(D("10"), D("1.00"), D("0.50"), D("1.50"), D("0.08"), D("1.58"))
    b = SupplyCost(D("20"), D("2.00"), D("0.50"), D("2.50"), D("0.13"), D("2.63"))
    total = sum_supply_costs([a, b])
    assert total.consumption_kwh == D("30")
    assert total.energy_pounds == D("3.00")
    assert total.standing_pounds == D("1.00")
    assert total.subtotal_pounds == D("4.00")
    assert total.vat_pounds == D("0.21")
    assert total.total_pounds == D("4.21")


def test_sum_supply_costs_empty_is_zero():
    total = sum_supply_costs([])
    assert total.total_pounds == D("0")
    assert total.consumption_kwh == D("0")


from octopus_compare.costing import month_slices


def test_month_slices_groups_by_calendar_month():
    daily = {
        date(2026, 3, 30): D("9"),
        date(2026, 3, 31): D("8"),
        date(2026, 4, 1): D("7"),
    }
    slices = month_slices(daily)
    assert [m for m, _ in slices] == [date(2026, 3, 1), date(2026, 4, 1)]
    assert slices[0][1] == {date(2026, 3, 30): D("9"), date(2026, 3, 31): D("8")}
    assert slices[1][1] == {date(2026, 4, 1): D("7")}


def test_month_slices_empty():
    assert month_slices({}) == []
