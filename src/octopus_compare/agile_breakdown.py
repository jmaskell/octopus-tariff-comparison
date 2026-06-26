from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from octopus_compare.money import pounds

_LONDON = ZoneInfo("Europe/London")
_UTC = ZoneInfo("UTC")


def _period_rates(rate_map: dict[datetime, Decimal], period_from: date,
                  period_to: date) -> dict[datetime, Decimal]:
    """rate_map restricted to instants in [period_from 00:00 UTC, period_to 00:00
    UTC] inclusive — the requested window, excluding the +1 boundary-day rates."""
    start = datetime(period_from.year, period_from.month, period_from.day, tzinfo=_UTC)
    end = datetime(period_to.year, period_to.month, period_to.day, tzinfo=_UTC)
    return {i: r for i, r in rate_map.items() if start <= i <= end}


@dataclass
class Decomposition:
    flex_p: Decimal             # Flexible effective unit price, exc-VAT p/kWh
    time_avg_p: Decimal         # Agile time-average (flat-user) price
    load_p: Decimal             # Agile load-weighted (actual) price
    structural_p: Decimal       # flex_p - time_avg_p  (>0: Agile cheaper on avg)
    behavioural_p: Decimal      # time_avg_p - load_p  (>0: you use at cheaper times)
    total_p: Decimal            # flex_p - load_p
    structural_pounds: Decimal  # over the period (signed)
    behavioural_pounds: Decimal
    total_pounds: Decimal
    total_kwh: Decimal


def compute_decomposition(period_rates: dict[datetime, Decimal],
                          flex_effective_p: Decimal, agile_effective_p: Decimal,
                          total_kwh: Decimal) -> Decomposition:
    if period_rates:
        time_avg = (sum(period_rates.values(), Decimal(0)) / len(period_rates)).quantize(Decimal("0.1"))
    else:
        time_avg = Decimal(0)
    structural = flex_effective_p - time_avg
    behavioural = time_avg - agile_effective_p
    total = flex_effective_p - agile_effective_p
    return Decomposition(
        flex_p=flex_effective_p, time_avg_p=time_avg, load_p=agile_effective_p,
        structural_p=structural, behavioural_p=behavioural, total_p=total,
        structural_pounds=pounds(structural * total_kwh),
        behavioural_pounds=pounds(behavioural * total_kwh),
        total_pounds=pounds(total * total_kwh),
        total_kwh=total_kwh,
    )
