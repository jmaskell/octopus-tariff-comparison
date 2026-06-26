from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from octopus_compare.agile import build_halfhourly_lookup

_UTC = ZoneInfo("UTC")


def test_halfhourly_lookup_by_utc_instant():
    results = [
        {"value_exc_vat": 22.5, "valid_from": "2026-03-01T16:00:00Z",
         "valid_to": "2026-03-01T16:30:00Z"},
        {"value_exc_vat": -1.8, "valid_from": "2026-03-01T13:30:00Z",
         "valid_to": "2026-03-01T14:00:00Z"},
    ]
    rates = build_halfhourly_lookup(results)
    assert rates.rate_for(datetime(2026, 3, 1, 16, 0, tzinfo=_UTC)) == Decimal("22.5")
    assert rates.rate_for(datetime(2026, 3, 1, 13, 30, tzinfo=_UTC)) == Decimal("-1.8")


def test_halfhourly_lookup_aligns_across_timezones():
    # A rate published with a +01:00 (BST) offset is found by the same instant
    # expressed in UTC — proves UTC-instant alignment over DST.
    rates = build_halfhourly_lookup(
        [{"value_exc_vat": 30.0, "valid_from": "2026-03-29T01:00:00+01:00",
          "valid_to": "2026-03-29T01:30:00+01:00"}])
    assert rates.rate_for(datetime(2026, 3, 29, 0, 0, tzinfo=_UTC)) == Decimal("30.0")


def test_halfhourly_lookup_missing_raises():
    rates = build_halfhourly_lookup([])
    with pytest.raises(KeyError):
        rates.rate_for(datetime(2026, 3, 1, 0, 0, tzinfo=_UTC))


from octopus_compare.agile import resolve_agile_versions, AgileVersion
from tests.fixtures.api_samples import AGILE_PRODUCTS_LIST


class AgileListClient:
    def __init__(self, results=AGILE_PRODUCTS_LIST):
        self._results = results

    def get_results(self, path, params=None):
        assert path == "products/"
        return self._results

    def get(self, path, params=None):
        code = path.split("/")[1]
        for r in AGILE_PRODUCTS_LIST:
            if r["code"] == code:
                return r
        raise AssertionError(code)


def test_resolve_agile_versions_filters_to_window():
    versions = resolve_agile_versions(
        AgileListClient(), date(2026, 1, 1), date(2026, 5, 31))
    codes = [v.product_code for v in versions]
    assert codes == ["AGILE-24-10-01"]          # only the current one covers 2026
    assert versions[0].available_to is None


def test_resolve_agile_versions_spans_multiple():
    versions = resolve_agile_versions(
        AgileListClient(), date(2024, 6, 1), date(2025, 1, 1))
    codes = [v.product_code for v in versions]
    assert codes == ["AGILE-23-12-06", "AGILE-24-10-01"]  # sorted by available_from


def test_resolve_agile_versions_override():
    versions = resolve_agile_versions(
        AgileListClient(), date(2026, 1, 1), date(2026, 5, 31), "AGILE-24-10-01")
    assert [v.product_code for v in versions] == ["AGILE-24-10-01"]


def test_resolve_agile_versions_none_raises():
    with pytest.raises(ValueError):
        resolve_agile_versions(AgileListClient(), date(2020, 1, 1), date(2020, 2, 1))
