from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from octopus_compare.account import MeterPoint, product_code_from_tariff
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
