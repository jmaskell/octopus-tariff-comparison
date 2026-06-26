from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from octopus_compare.costing import SupplyCost, standing_pence
from octopus_compare.money import pounds, round_pence, vat_pence

_LONDON = ZoneInfo("Europe/London")


def _local_date(instant: datetime) -> date:
    return instant.astimezone(_LONDON).date()


def agile_energy_pence(
    halfhourly_kwh: dict[datetime, Decimal],
    rate_p_for: Callable[[datetime], Decimal],
) -> Decimal:
    """Sum over London-local days of round_half_up(sum of that day's
    half-hourly kwh × exc-VAT rate), in pence. One rounding per day, matching
    the daily engine; negative rates reduce the total."""
    by_day: dict[date, Decimal] = {}
    for instant, kwh in halfhourly_kwh.items():
        day = _local_date(instant)
        by_day[day] = by_day.get(day, Decimal(0)) + Decimal(kwh) * Decimal(rate_p_for(instant))
    return sum((round_pence(v) for v in by_day.values()), Decimal(0))


def agile_supply_cost(
    halfhourly_kwh: dict[datetime, Decimal],
    rate_p_for: Callable[[datetime], Decimal],
    sc_p_for: Callable[[date], Decimal],
) -> SupplyCost:
    days = sorted({_local_date(i) for i in halfhourly_kwh})
    energy_p = agile_energy_pence(halfhourly_kwh, rate_p_for)
    sc_p = standing_pence(days, sc_p_for)
    subtotal_p = energy_p + sc_p
    vat_p = vat_pence(subtotal_p)
    total_p = subtotal_p + vat_p
    consumption = sum((Decimal(v) for v in halfhourly_kwh.values()), Decimal(0))
    return SupplyCost(
        consumption_kwh=consumption,
        energy_pounds=pounds(energy_p),
        standing_pounds=pounds(sc_p),
        subtotal_pounds=pounds(subtotal_p),
        vat_pounds=pounds(vat_p),
        total_pounds=pounds(total_p),
    )
