from datetime import datetime
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
