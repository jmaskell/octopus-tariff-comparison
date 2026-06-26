from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal


@dataclass
class SupplyCoverage:
    supply: str
    priced_days: int
    expected_days: int
    missing_months: list[date]


@dataclass
class Coverage:
    per_supply: list[SupplyCoverage]
    notes: list[str]

    @property
    def complete(self) -> bool:
        return (
            not self.notes
            and all(s.priced_days >= s.expected_days for s in self.per_supply)
        )


def _days(start: date, end: date):
    """Yield each date in [start, end)."""
    d = start
    while d < end:
        yield d
        d += timedelta(days=1)


def compare_coverage(
    period_from: date,
    period_to: date,
    priced_days_by_supply: dict[str, set[date]],
) -> Coverage:
    """Coverage for the 3-way compare.

    `expected` is the requested window [period_from, period_to) trimmed to the
    span actually backed by data on at least one supply (so unsettled recent
    days, and a not-yet-started leading edge, never count as missing). A supply
    is short if it lacks any day inside that shared span.
    """
    in_window = {
        d
        for days in priced_days_by_supply.values()
        for d in days
        if period_from <= d < period_to
    }
    if not in_window:
        per = [
            SupplyCoverage(s, 0, 0, []) for s in priced_days_by_supply
        ]
        return Coverage(per, ["no consumption data in the requested window"])

    span_start, span_end = min(in_window), max(in_window)
    expected = set(_days(span_start, span_end + timedelta(days=1)))

    per_supply = []
    for supply, days in priced_days_by_supply.items():
        present = {d for d in days if d in expected}
        missing = expected - present
        missing_months = sorted({m.replace(day=1) for m in missing})
        per_supply.append(
            SupplyCoverage(supply, len(present), len(expected), missing_months)
        )
    return Coverage(per_supply, [])


@dataclass
class AgileCoverage:
    daily_days: int
    hh_days: int
    missing_hh_days: list[date]
    daily_kwh: Decimal
    hh_kwh: Decimal
    divergence_pct: Decimal
    notes: list[str]

    @property
    def complete(self) -> bool:
        return not self.missing_hh_days and not self.notes


def agile_coverage(
    daily_days: set[date],
    hh_local_days: set[date],
    daily_kwh: Decimal,
    hh_kwh: Decimal,
    divergence_threshold: Decimal = Decimal("2"),
) -> AgileCoverage:
    """Coverage for the Agile compare: every day with daily data must have
    half-hourly data, and the two totals must agree within `divergence_threshold`%."""
    missing = sorted(daily_days - hh_local_days)
    if daily_kwh > 0:
        divergence = (abs(daily_kwh - hh_kwh) / daily_kwh * 100).quantize(Decimal("0.1"))
    else:
        divergence = Decimal(0)
    notes: list[str] = []
    if divergence > divergence_threshold:
        notes.append(
            f"half-hourly total ({hh_kwh} kWh) differs from daily total "
            f"({daily_kwh} kWh) by {divergence}%"
        )
    return AgileCoverage(
        daily_days=len(daily_days),
        hh_days=len(hh_local_days),
        missing_hh_days=missing,
        daily_kwh=daily_kwh,
        hh_kwh=hh_kwh,
        divergence_pct=divergence,
        notes=notes,
    )
