from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from octopus_compare.units import m3_to_kwh

LONDON = ZoneInfo("Europe/London")
UTC = ZoneInfo("UTC")


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


def _resolve_gas_units(raw: dict[date, Decimal], gas_units: str) -> str:
    if gas_units in ("m3", "kwh"):
        return gas_units
    if not raw:
        return "m3"
    mean = sum(raw.values(), Decimal(0)) / len(raw)
    return "kwh" if mean > 15 else "m3"


def to_kwh(raw, supply, gas_units, calorific_value):
    if supply == "electricity":
        return raw
    resolved = _resolve_gas_units(raw, gas_units)
    if resolved == "kwh":
        return raw
    return {d: m3_to_kwh(v, calorific_value) for d, v in raw.items()}
