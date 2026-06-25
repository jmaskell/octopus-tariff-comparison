from datetime import date
from decimal import Decimal

from octopus_compare.consumption import fetch_daily, to_kwh
from tests.fixtures.api_samples import ELEC_CONSUMPTION_KWH


class FakeClient:
    def __init__(self, results):
        self._results = results
        self.paths = []

    def get_results(self, path, params=None):
        self.paths.append(path)
        return self._results


def test_fetch_daily_buckets_by_local_date():
    client = FakeClient(ELEC_CONSUMPTION_KWH["results"])
    daily = fetch_daily(client, "electricity", "1200033187430", ["19L3474725"],
                        date(2026, 3, 1), date(2026, 3, 2))
    assert daily == {date(2026, 3, 1): Decimal("9.09")}
    assert client.paths == [
        "electricity-meter-points/1200033187430/meters/19L3474725/consumption/"]


def test_fetch_daily_sums_across_meters():
    # A decommissioned meter returns nothing; the active meter returns the data.
    by_serial = {
        "OLD": [],
        "NEW": [{"consumption": 9.09, "interval_start": "2026-03-01T00:00:00Z",
                 "interval_end": "2026-03-02T00:00:00Z"}],
    }

    class MultiMeterClient:
        def __init__(self):
            self.serials_called = []

        def get_results(self, path, params=None):
            serial = path.split("/meters/")[1].split("/")[0]
            self.serials_called.append(serial)
            return by_serial[serial]

    client = MultiMeterClient()
    daily = fetch_daily(client, "electricity", "1200033187430", ["OLD", "NEW"],
                        date(2026, 3, 1), date(2026, 3, 2))
    assert daily == {date(2026, 3, 1): Decimal("9.09")}
    assert client.serials_called == ["OLD", "NEW"]


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
