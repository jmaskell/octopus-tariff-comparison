from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

LONDON = ZoneInfo("Europe/London")


def _to_london_date(value: str | None, default: date) -> date:
    if not value:
        return default
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt.astimezone(LONDON).date()


@dataclass
class _Window:
    start: date
    end: date
    value: Decimal


class RateLookup:
    def __init__(self, windows: list[_Window]):
        self._windows = windows

    def rate_for(self, day: date) -> Decimal:
        for w in self._windows:
            if w.start <= day < w.end:
                return w.value
        raise KeyError(f"No rate covering {day}")


def build_lookup(results: list[dict]) -> RateLookup:
    windows = []
    for r in results:
        windows.append(
            _Window(
                start=_to_london_date(r.get("valid_from"), date.min),
                end=_to_london_date(r.get("valid_to"), date.max),
                value=Decimal(str(r["value_exc_vat"])),
            )
        )
    return RateLookup(windows)


def _iso(d: date) -> str:
    return d.strftime("%Y-%m-%dT00:00:00Z")


def fetch_rates(client, supply, product_code, tariff_code, period_from, period_to):
    path = f"products/{product_code}/{supply}-tariffs/{tariff_code}/standard-unit-rates/"
    results = client.get_results(
        path, {"period_from": _iso(period_from), "period_to": _iso(period_to)}
    )
    return build_lookup(results)


def fetch_standing_charges(client, supply, product_code, tariff_code, period_from, period_to):
    path = f"products/{product_code}/{supply}-tariffs/{tariff_code}/standing-charges/"
    results = client.get_results(
        path, {"period_from": _iso(period_from), "period_to": _iso(period_to)}
    )
    return build_lookup(results)
