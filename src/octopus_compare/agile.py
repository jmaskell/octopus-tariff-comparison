from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from octopus_compare.account import build_tariff_code
from octopus_compare.rates import fetch_standing_charges, VersionedLookup

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
# AGILE-OUTGOING-* is the export/Outgoing tariff (selling power back), not an
# import tariff — it must be excluded from the consumption comparison.
_OUTGOING_PREFIX = "AGILE-OUTGOING"


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
        and not r.get("code", "").startswith(_OUTGOING_PREFIX)
    ]
    in_window = [
        v for v in versions
        if v.available_from < period_to and (v.available_to or date.max) > period_from
    ]
    if not in_window:
        raise ValueError("No Octopus Agile product covering this window was found")
    return sorted(in_window, key=lambda v: v.available_from)


def _iso(d: date) -> str:
    return d.strftime("%Y-%m-%dT00:00:00Z")


def agile_resolvers(client, versions, region, period_from, period_to):
    """(rate_for, sc_for) for the Agile column. Half-hourly unit rates from every
    version are merged into one instant-keyed lookup (version windows never
    overlap). Standing charges are daily and version-selected via VersionedLookup,
    mirroring tracker_resolvers."""
    by_instant: dict[datetime, Decimal] = {}
    sc_entries = []
    single = len(versions) == 1
    # The consumption endpoint includes the half-hour at exactly period_to (00:00
    # of the --to date), but the rates/standing-charges endpoints are exclusive at
    # period_to. Fetch one extra day so that boundary half-hour has a covering rate.
    fetch_to = period_to + timedelta(days=1)
    for v in versions:
        tariff = build_tariff_code("electricity", v.product_code, region)
        rate_results = client.get_results(
            f"products/{v.product_code}/electricity-tariffs/{tariff}/standard-unit-rates/",
            {"period_from": _iso(period_from), "period_to": _iso(fetch_to),
             "page_size": 25000},
        )
        for r in rate_results:
            by_instant[_utc_instant(r["valid_from"])] = Decimal(str(r["value_exc_vat"]))
        v_from, v_to = (date.min, None) if single else (v.available_from, v.available_to)
        sc_entries.append((
            v_from, v_to,
            fetch_standing_charges(client, "electricity", v.product_code, tariff,
                                   period_from, fetch_to),
        ))
    return HalfHourlyRates(by_instant).rate_for, VersionedLookup(sc_entries).rate_for
