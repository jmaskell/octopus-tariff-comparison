from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from octopus_compare.units import m3_to_kwh, VOLUME_CORRECTION

LONDON = ZoneInfo("Europe/London")
UTC = ZoneInfo("UTC")

GAS_AMBIGUOUS_LOW = Decimal("4")
GAS_AMBIGUOUS_HIGH = Decimal("25")


@dataclass
class GasUnitInfo:
    requested: str
    resolved: str
    confident: bool
    factor: Decimal | None  # kWh per m3 when converting, else None


def _local_date(value: str) -> date:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(LONDON).date()


def _iso(d: date) -> str:
    return d.strftime("%Y-%m-%dT00:00:00Z")


def _utc_instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def fetch_daily(client, supply, identifier, serials, period_from, period_to):
    """Daily consumption summed across every meter on the point, keyed by the
    Europe/London date of interval_start.

    A meter point can have several meters over time (meter swaps). A
    decommissioned meter returns no data for a given period and the active one
    returns it; meters never overlap in time, so summing across all of them
    never double-counts and correctly covers a period that spans a swap.
    """
    daily: dict[date, Decimal] = {}
    for serial in serials:
        path = f"{supply}-meter-points/{identifier}/meters/{serial}/consumption/"
        results = client.get_results(
            path,
            {
                "period_from": _iso(period_from),
                "period_to": _iso(period_to),
                "group_by": "day",
                "order_by": "period",
                "page_size": 25000,
            },
        )
        for r in results:
            day = _local_date(r["interval_start"])
            daily[day] = daily.get(day, Decimal(0)) + Decimal(str(r["consumption"]))
    return daily


def fetch_halfhourly(client, identifier, serials, period_from, period_to):
    """Half-hourly electricity consumption summed across the point's serials,
    keyed by the UTC instant of interval_start so it aligns to Agile rate
    windows regardless of GMT/BST. Electricity only."""
    half: dict[datetime, Decimal] = {}
    for serial in serials:
        path = f"electricity-meter-points/{identifier}/meters/{serial}/consumption/"
        results = client.get_results(
            path,
            {
                "period_from": _iso(period_from),
                "period_to": _iso(period_to),
                "order_by": "period",
                "page_size": 25000,
            },
        )
        for r in results:
            instant = _utc_instant(r["interval_start"])
            half[instant] = half.get(instant, Decimal(0)) + Decimal(str(r["consumption"]))
    return half


def _resolve_gas_units(raw: dict[date, Decimal], gas_units: str) -> tuple[str, bool]:
    if gas_units in ("m3", "kwh"):
        return gas_units, True
    if not raw:
        return "m3", False
    mean = sum(raw.values(), Decimal(0)) / len(raw)
    unit = "kwh" if mean > 15 else "m3"
    confident = not (GAS_AMBIGUOUS_LOW <= mean < GAS_AMBIGUOUS_HIGH)
    return unit, confident


def gas_unit_info(
    raw: dict[date, Decimal], gas_units: str, calorific_value: Decimal
) -> GasUnitInfo:
    resolved, confident = _resolve_gas_units(raw, gas_units)
    factor = (
        VOLUME_CORRECTION * Decimal(calorific_value) / Decimal("3.6")
        if resolved == "m3"
        else None
    )
    return GasUnitInfo(gas_units, resolved, confident, factor)


def to_kwh(raw, supply, gas_units, calorific_value):
    if supply == "electricity":
        return raw
    resolved, _ = _resolve_gas_units(raw, gas_units)
    if resolved == "kwh":
        return raw
    return {d: m3_to_kwh(v, calorific_value) for d, v in raw.items()}
