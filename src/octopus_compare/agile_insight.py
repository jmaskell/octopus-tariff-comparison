from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

from octopus_compare.money import pounds

_LONDON = ZoneInfo("Europe/London")


@dataclass
class HalfHourStat:
    when: datetime          # London local
    rate_p: Decimal         # exc-VAT pence/kWh
    kwh: Decimal
    cost_pounds: Decimal    # exc-VAT


@dataclass
class AgileInsight:
    agile_effective_p: Decimal      # exc-VAT pence/kWh
    flex_effective_p: Decimal
    peak_window: tuple
    peak_kwh: Decimal
    offpeak_kwh: Decimal
    peak_pct: Decimal
    peak_agile_pounds: Decimal      # exc-VAT
    peak_flex_pounds: Decimal
    cheapest: HalfHourStat
    priciest: HalfHourStat
    negative_count: int


def _effective_p(energy_p: Decimal, total_kwh: Decimal) -> Decimal:
    if total_kwh == 0:
        return Decimal(0)
    return (energy_p / total_kwh).quantize(Decimal("0.1"))


def compute_insight(
    halfhourly_kwh: dict[datetime, Decimal],
    agile_rate_for: Callable[[datetime], Decimal],
    flex_rate_for: Callable[[date], Decimal],
    peak_window: tuple,
) -> AgileInsight:
    start, end = peak_window
    total_kwh = agile_energy_p = flex_energy_p = Decimal(0)
    peak_kwh = peak_agile_p = peak_flex_p = Decimal(0)
    negative_count = 0
    cheapest = priciest = None
    for instant, kwh in halfhourly_kwh.items():
        local = instant.astimezone(_LONDON)
        a_rate = Decimal(agile_rate_for(instant))
        f_rate = Decimal(flex_rate_for(local.date()))
        a_cost = Decimal(kwh) * a_rate
        total_kwh += Decimal(kwh)
        agile_energy_p += a_cost
        flex_energy_p += Decimal(kwh) * f_rate
        if a_rate < 0:
            negative_count += 1
        if start <= local.time() < end:
            peak_kwh += Decimal(kwh)
            peak_agile_p += a_cost
            peak_flex_p += Decimal(kwh) * f_rate
        stat = HalfHourStat(local, a_rate, Decimal(kwh), pounds(a_cost))
        if cheapest is None or a_rate < cheapest.rate_p:
            cheapest = stat
        if priciest is None or a_rate > priciest.rate_p:
            priciest = stat
    peak_pct = (peak_kwh / total_kwh * 100).quantize(Decimal("0.1")) if total_kwh else Decimal(0)
    return AgileInsight(
        agile_effective_p=_effective_p(agile_energy_p, total_kwh),
        flex_effective_p=_effective_p(flex_energy_p, total_kwh),
        peak_window=peak_window,
        peak_kwh=peak_kwh,
        offpeak_kwh=total_kwh - peak_kwh,
        peak_pct=peak_pct,
        peak_agile_pounds=pounds(peak_agile_p),
        peak_flex_pounds=pounds(peak_flex_p),
        cheapest=cheapest,
        priciest=priciest,
        negative_count=negative_count,
    )
