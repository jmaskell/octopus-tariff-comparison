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
