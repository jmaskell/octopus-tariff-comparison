from datetime import date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

from octopus_compare.agile_insight import compute_insight

_UTC = ZoneInfo("UTC")
PEAK = (time(16, 0), time(19, 0))


def _agile_rate(instant):
    # 16:00 UTC slot is dear, the 00:00 slot is cheap (negative).
    return Decimal("30.0") if instant.hour == 16 else Decimal("-2.0")


def _flex_rate(_day):
    return Decimal("24.0")


def test_compute_insight_peak_and_effective_price():
    kwh = {
        datetime(2026, 3, 1, 0, 0, tzinfo=_UTC): Decimal("1.0"),    # off-peak, -2p
        datetime(2026, 3, 1, 16, 0, tzinfo=_UTC): Decimal("1.0"),   # peak (16:00 London), 30p
    }
    ins = compute_insight(kwh, _agile_rate, _flex_rate, PEAK)
    # agile energy = (1*-2 + 1*30) = 28p over 2 kWh -> 14.0 p/kWh
    assert ins.agile_effective_p == Decimal("14.0")
    assert ins.flex_effective_p == Decimal("24.0")
    assert ins.peak_pct == Decimal("50.0")
    assert ins.peak_kwh == Decimal("1.0")
    assert ins.negative_count == 1
    assert ins.cheapest.rate_p == Decimal("-2.0")
    assert ins.priciest.rate_p == Decimal("30.0")
    assert ins.priciest.when.hour == 16        # London local hour
