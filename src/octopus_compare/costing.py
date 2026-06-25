from collections.abc import Callable
from datetime import date
from decimal import Decimal

from octopus_compare.money import round_pence


def daily_energy_pence(
    daily_kwh: dict[date, Decimal],
    rate_p_for: Callable[[date], Decimal],
) -> Decimal:
    """Sum of per-day round_half_up(kwh * exc-VAT rate), in pence."""
    total = Decimal(0)
    for day, kwh in daily_kwh.items():
        total += round_pence(Decimal(kwh) * Decimal(rate_p_for(day)))
    return total
