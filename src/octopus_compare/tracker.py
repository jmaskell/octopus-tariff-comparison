from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from octopus_compare.account import MeterPoint, product_code_from_tariff, build_tariff_code
from octopus_compare.rates import fetch_rates, fetch_standing_charges, VersionedLookup, flat_lookup
from octopus_compare.client import ApiError


@dataclass
class TrackerTariff:
    product_code: str
    tariff_code: str


def resolve_tracker(client, meter_point: MeterPoint) -> TrackerTariff:
    """Most recent Octopus Tracker tariff in this meter's agreement history.

    Octopus Tracker (product codename SILVER) is NOT in the public /products/
    list, so it cannot be found by listing. But every product the account has
    been on is reachable via GET /products/{code}/, which reports is_tracker,
    and a tracker tariff keeps publishing daily unit rates well beyond the
    agreement period. So we walk the meter's agreements newest-first and return
    the first whose product is a tracker, using the household's own
    region-specific tariff code for it.
    """
    is_tracker: dict[str, bool] = {}
    for agreement in sorted(
        meter_point.agreements,
        key=lambda a: a.valid_from or date.min,
        reverse=True,
    ):
        product = product_code_from_tariff(agreement.tariff_code)
        if product not in is_tracker:
            detail = client.get(f"products/{product}/")
            is_tracker[product] = bool(detail.get("is_tracker"))
        if is_tracker[product]:
            return TrackerTariff(
                product_code=product, tariff_code=agreement.tariff_code
            )
    raise ValueError("No Tracker tariff found in this account's agreement history")


_LONDON = ZoneInfo("Europe/London")


@dataclass
class TrackerVersion:
    product_code: str
    display_name: str
    available_from: date
    available_to: date | None


def _to_date(value: str | None) -> date | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(_LONDON).date()


def _version_from_detail(code: str, detail: dict) -> TrackerVersion:
    return TrackerVersion(
        product_code=code,
        display_name=detail.get("full_name") or detail.get("display_name") or code,
        available_from=_to_date(detail.get("available_from")),
        available_to=_to_date(detail.get("available_to")),
    )


def _next_code(product_code: str, available_to: date) -> str:
    codename = "-".join(product_code.split("-")[:-3])
    return f"{codename}-{available_to:%y-%m-%d}"


def discover_chain(client, seed_product: str) -> list[TrackerVersion]:
    versions: list[TrackerVersion] = []
    code: str | None = seed_product
    seen: set[str] = set()
    while code and code not in seen:
        seen.add(code)
        try:
            detail = client.get(f"products/{code}/")
        except ApiError:
            break
        version = _version_from_detail(code, detail)
        versions.append(version)
        if version.available_to is None:
            break
        code = _next_code(code, version.available_to)
    return versions


def _tracker_anchors(client, meter_point) -> list[str]:
    """Distinct Tracker product codes in the meter's agreement history, newest-first."""
    anchors: list[str] = []
    seen: set[str] = set()
    for agreement in sorted(
        meter_point.agreements, key=lambda a: a.valid_from or date.min, reverse=True
    ):
        product = product_code_from_tariff(agreement.tariff_code)
        if product in seen:
            continue
        seen.add(product)
        if client.get(f"products/{product}/").get("is_tracker"):
            anchors.append(product)
    return anchors


def tracker_versions_for_window(
    client, meter_point, period_from: date, period_to: date
) -> list[TrackerVersion]:
    anchors = _tracker_anchors(client, meter_point)
    if not anchors:
        raise ValueError("No Tracker tariff found in this account's agreement history")
    by_code = {v.product_code: v for v in discover_chain(client, anchors[0])}
    for code in anchors[1:]:
        if code not in by_code:
            by_code[code] = _version_from_detail(code, client.get(f"products/{code}/"))
    versions = sorted(by_code.values(), key=lambda v: v.available_from)
    return [
        v for v in versions
        if v.available_from < period_to and (v.available_to or date.max) > period_from
    ]


def latest_tracker_version(versions: list[TrackerVersion]) -> TrackerVersion:
    for version in versions:
        if version.available_to is None:
            return version
    return max(versions, key=lambda v: v.available_from)


@dataclass
class FlexibleTariff:
    product_code: str
    tariff_code: str


def resolve_flexible(client, meter_point) -> FlexibleTariff:
    for agreement in sorted(
        meter_point.agreements, key=lambda a: a.valid_from or date.min, reverse=True
    ):
        product = product_code_from_tariff(agreement.tariff_code)
        if not client.get(f"products/{product}/").get("is_tracker"):
            return FlexibleTariff(product_code=product, tariff_code=agreement.tariff_code)
    raise ValueError("No Flexible tariff found in this account's agreement history")


def tracker_resolvers(client, supply, versions, region, period_from, period_to):
    rate_entries = []
    sc_entries = []
    single = len(versions) == 1
    for version in versions:
        tariff = build_tariff_code(supply, version.product_code, region)
        if single:
            v_from, v_to = date.min, None
        else:
            v_from, v_to = version.available_from, version.available_to
        rate_entries.append((
            v_from, v_to,
            fetch_rates(client, supply, version.product_code, tariff, period_from, period_to),
        ))
        sc_entries.append((
            v_from, v_to,
            fetch_standing_charges(client, supply, version.product_code, tariff, period_from, period_to),
        ))
    return VersionedLookup(rate_entries).rate_for, VersionedLookup(sc_entries).rate_for


_FIXED_PREFIX = "OE-FIX-12M-"


@dataclass
class FixedProduct:
    product_code: str
    display_name: str
    available_from: date


def resolve_fixed(client, override: str | None = None) -> FixedProduct:
    if override:
        detail = client.get(f"products/{override}/")
        return FixedProduct(
            override,
            detail.get("full_name") or detail.get("display_name") or override,
            _to_date(detail.get("available_from")),
        )
    results = client.get_results("products/", {"brand": "OCTOPUS_ENERGY"})
    candidates = [r for r in results if r.get("code", "").startswith(_FIXED_PREFIX)]
    if not candidates:
        raise ValueError("No Octopus 12M Fixed product found in the product list")
    current = [r for r in candidates if not r.get("available_to")]
    pool = current or candidates
    best = max(pool, key=lambda r: _to_date(r.get("available_from")) or date.min)
    return FixedProduct(
        best["code"],
        best.get("full_name") or best.get("display_name") or best["code"],
        _to_date(best.get("available_from")),
    )


def fixed_resolvers(client, supply, product, region):
    """Per-day resolvers for the 12M Fixed column: the product's locked rate is
    fetched once (at its own available_from) and applied flat to every day."""
    tariff = build_tariff_code(supply, product.product_code, region)
    anchor = product.available_from
    rates = fetch_rates(client, supply, product.product_code, tariff,
                        anchor, anchor + timedelta(days=1))
    sc = fetch_standing_charges(client, supply, product.product_code, tariff,
                                anchor, anchor + timedelta(days=1))
    rate_value = rates.rate_for(anchor)
    sc_value = sc.rate_for(anchor)
    return flat_lookup(rate_value).rate_for, flat_lookup(sc_value).rate_for
