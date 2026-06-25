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
