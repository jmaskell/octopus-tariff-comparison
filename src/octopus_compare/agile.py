from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

_UTC = ZoneInfo("UTC")


def _utc_instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(_UTC)


class HalfHourlyRates:
    """Agile unit rates keyed by the UTC instant of each half-hour's valid_from.
    Agile publishes exactly one aligned 30-minute window per slot, so an exact
    instant match is correct (and version windows never overlap, so merging the
    dicts of several versions is unambiguous)."""

    def __init__(self, by_instant: dict[datetime, Decimal]):
        self._by_instant = by_instant

    def rate_for(self, instant: datetime) -> Decimal:
        try:
            return self._by_instant[instant]
        except KeyError as e:
            raise KeyError(f"No Agile rate covering {instant.isoformat()}") from e


def build_halfhourly_lookup(results: list[dict]) -> HalfHourlyRates:
    by_instant: dict[datetime, Decimal] = {}
    for r in results:
        by_instant[_utc_instant(r["valid_from"])] = Decimal(str(r["value_exc_vat"]))
    return HalfHourlyRates(by_instant)


_AGILE_PREFIX = "AGILE-"


def _to_date(value: str | None) -> date | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(_UTC).date()


@dataclass
class AgileVersion:
    product_code: str
    display_name: str
    available_from: date
    available_to: date | None


def _version(code: str, d: dict) -> AgileVersion:
    return AgileVersion(
        product_code=code,
        display_name=d.get("full_name") or d.get("display_name") or code,
        available_from=_to_date(d.get("available_from")),
        available_to=_to_date(d.get("available_to")),
    )


def resolve_agile_versions(client, period_from, period_to, override=None):
    """Agile versions whose availability window intersects [period_from,
    period_to). Sourced from the public product list (Agile is listed). The
    override pins a single version."""
    if override:
        return [_version(override, client.get(f"products/{override}/"))]
    results = client.get_results("products/", {"brand": "OCTOPUS_ENERGY"})
    versions = [
        _version(r["code"], r)
        for r in results
        if r.get("code", "").startswith(_AGILE_PREFIX)
    ]
    in_window = [
        v for v in versions
        if v.available_from < period_to and (v.available_to or date.max) > period_from
    ]
    if not in_window:
        raise ValueError("No Octopus Agile product covering this window was found")
    return sorted(in_window, key=lambda v: v.available_from)
