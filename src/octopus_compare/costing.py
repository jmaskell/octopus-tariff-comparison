from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from octopus_compare.money import pounds, round_pence, vat_pence


def daily_energy_pence(
    daily_kwh: dict[date, Decimal],
    rate_p_for: Callable[[date], Decimal],
) -> Decimal:
    """Sum of per-day round_half_up(kwh * exc-VAT rate), in pence."""
    total = Decimal(0)
    for day, kwh in daily_kwh.items():
        total += round_pence(Decimal(kwh) * Decimal(rate_p_for(day)))
    return total


def standing_pence(
    days: list[date],
    sc_p_for: Callable[[date], Decimal],
) -> Decimal:
    """Round_half_up of the summed per-day exc-VAT standing charge, in pence."""
    total = sum((Decimal(sc_p_for(d)) for d in days), Decimal(0))
    return round_pence(total)


@dataclass
class SupplyCost:
    consumption_kwh: Decimal
    energy_pounds: Decimal
    standing_pounds: Decimal
    subtotal_pounds: Decimal
    vat_pounds: Decimal
    total_pounds: Decimal


def supply_cost(
    daily_kwh: dict[date, Decimal],
    rate_p_for: Callable[[date], Decimal],
    sc_p_for: Callable[[date], Decimal],
) -> SupplyCost:
    days = sorted(daily_kwh)
    energy_p = daily_energy_pence(daily_kwh, rate_p_for)
    sc_p = standing_pence(days, sc_p_for)
    subtotal_p = energy_p + sc_p
    vat_p = vat_pence(subtotal_p)
    total_p = subtotal_p + vat_p
    consumption = sum((Decimal(v) for v in daily_kwh.values()), Decimal(0))
    return SupplyCost(
        consumption_kwh=consumption,
        energy_pounds=pounds(energy_p),
        standing_pounds=pounds(sc_p),
        subtotal_pounds=pounds(subtotal_p),
        vat_pounds=pounds(vat_p),
        total_pounds=pounds(total_p),
    )


def sum_supply_costs(costs: list[SupplyCost]) -> SupplyCost:
    z = Decimal(0)

    def s(attr: str) -> Decimal:
        return sum((getattr(c, attr) for c in costs), z)

    return SupplyCost(
        consumption_kwh=s("consumption_kwh"),
        energy_pounds=s("energy_pounds"),
        standing_pounds=s("standing_pounds"),
        subtotal_pounds=s("subtotal_pounds"),
        vat_pounds=s("vat_pounds"),
        total_pounds=s("total_pounds"),
    )


def month_slices(
    daily_kwh: dict[date, Decimal],
) -> list[tuple[date, dict[date, Decimal]]]:
    buckets: dict[date, dict[date, Decimal]] = {}
    for day, kwh in daily_kwh.items():
        buckets.setdefault(day.replace(day=1), {})[day] = kwh
    return [(month, buckets[month]) for month in sorted(buckets)]
