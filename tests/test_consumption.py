from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from octopus_compare.consumption import (
    _resolve_gas_units,
    fetch_daily,
    fetch_halfhourly,
    gas_unit_info,
    GasUnitInfo,
    to_kwh,
)
from tests.fixtures.api_samples import ELEC_CONSUMPTION_KWH, HH_CONSUMPTION

_UTC = ZoneInfo("UTC")


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


def test_fetch_halfhourly_keys_by_utc_instant():
    client = FakeClient(HH_CONSUMPTION["results"])
    half = fetch_halfhourly(client, "1200033187430", ["19L3474725"],
                            date(2026, 3, 1), date(2026, 3, 2))
    assert half[datetime(2026, 3, 1, 0, 0, tzinfo=_UTC)] == Decimal("0.20")
    assert half[datetime(2026, 3, 1, 16, 0, tzinfo=_UTC)] == Decimal("0.90")
    assert len(half) == 4
    assert client.paths == [
        "electricity-meter-points/1200033187430/meters/19L3474725/consumption/"]


def test_fetch_halfhourly_sums_across_meters():
    rows = HH_CONSUMPTION["results"]

    class MultiMeterClient:
        def get_results(self, path, params=None):
            serial = path.split("/meters/")[1].split("/")[0]
            return rows if serial == "NEW" else []

    half = fetch_halfhourly(MultiMeterClient(), "1200033187430", ["OLD", "NEW"],
                            date(2026, 3, 1), date(2026, 3, 2))
    assert half[datetime(2026, 3, 1, 0, 0, tzinfo=_UTC)] == Decimal("0.20")


# Task 3: Gas-unit confidence tests
def _raw(mean):
    # 10 days all equal to `mean`
    return {date(2026, 1, d): Decimal(str(mean)) for d in range(1, 11)}


def test_explicit_units_are_confident():
    assert _resolve_gas_units(_raw(8), "m3") == ("m3", True)
    assert _resolve_gas_units(_raw(8), "kwh") == ("kwh", True)


def test_auto_high_mean_is_confident_kwh():
    assert _resolve_gas_units(_raw(40), "auto") == ("kwh", True)


def test_auto_low_mean_is_confident_m3():
    assert _resolve_gas_units(_raw(2), "auto") == ("m3", True)


def test_auto_ambiguous_band_is_not_confident():
    unit, confident = _resolve_gas_units(_raw(8), "auto")
    assert confident is False  # 8 is in [4, 25)


def test_auto_empty_is_not_confident():
    assert _resolve_gas_units({}, "auto") == ("m3", False)


def test_gas_unit_info_reports_factor_for_m3():
    info = gas_unit_info(_raw(2), "auto", Decimal("39.5"))
    assert info == GasUnitInfo(
        requested="auto", resolved="m3", confident=True,
        factor=(Decimal("1.02264") * Decimal("39.5") / Decimal("3.6")),
    )


def test_gas_unit_info_no_factor_for_kwh():
    info = gas_unit_info(_raw(40), "auto", Decimal("39.5"))
    assert info.resolved == "kwh"
    assert info.factor is None
