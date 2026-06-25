from datetime import date
from decimal import Decimal

from octopus_compare.consumption import fetch_daily, to_kwh
from tests.fixtures.api_samples import GAS_CONSUMPTION_M3, ELEC_CONSUMPTION_KWH


class FakeClient:
    def __init__(self, results):
        self._results = results
        self.path = None

    def get_results(self, path, params=None):
        self.path = path
        return self._results


def test_fetch_daily_buckets_by_local_date():
    client = FakeClient(ELEC_CONSUMPTION_KWH["results"])
    daily = fetch_daily(client, "electricity", "1200033187430", "19L3474725",
                        date(2026, 3, 1), date(2026, 3, 2))
    assert daily == {date(2026, 3, 1): Decimal("9.09")}
    assert client.path == (
        "electricity-meter-points/1200033187430/meters/19L3474725/consumption/")


def test_gas_auto_detects_m3_and_converts():
    raw = {date(2026, 3, 1): Decimal("3.52")}
    kwh = to_kwh(raw, "gas", "auto", Decimal("39.2"))
    # 3.52 × 1.02264 × 39.2 / 3.6 ≈ 39.19
    assert abs(kwh[date(2026, 3, 1)] - Decimal("39.19")) <= Decimal("0.1")


def test_gas_explicit_kwh_passthrough():
    raw = {date(2026, 3, 1): Decimal("39.2")}
    kwh = to_kwh(raw, "gas", "kwh", Decimal("39.5"))
    assert kwh[date(2026, 3, 1)] == Decimal("39.2")


def test_electricity_passthrough():
    raw = {date(2026, 3, 1): Decimal("9.09")}
    assert to_kwh(raw, "electricity", "auto", Decimal("39.5")) == raw
