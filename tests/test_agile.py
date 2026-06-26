from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from octopus_compare.agile import build_halfhourly_lookup, resolve_agile_versions, AgileVersion, agile_resolvers
from tests.fixtures.api_samples import AGILE_PRODUCTS_LIST

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


class AgileRateClient:
    """Serves half-hourly Agile rates and a flat standing charge."""

    def get_results(self, path, params=None):
        if "standing-charges" in path:
            return [{"value_exc_vat": 45.0, "valid_from": None, "valid_to": None}]
        # standard-unit-rates: two aligned half-hours for 2026-03-01.
        return [
            {"value_exc_vat": 21.0, "valid_from": "2026-03-01T16:00:00Z",
             "valid_to": "2026-03-01T16:30:00Z"},
            {"value_exc_vat": -2.0, "valid_from": "2026-03-01T13:30:00Z",
             "valid_to": "2026-03-01T14:00:00Z"},
        ]


def test_agile_resolvers_single_version():
    v = AgileVersion("AGILE-24-10-01", "Agile Octopus", date(2024, 10, 1), None)
    rate_for, sc_for, rate_map = agile_resolvers(
        AgileRateClient(), [v], "C", date(2026, 3, 1), date(2026, 3, 2))
    assert rate_for(datetime(2026, 3, 1, 16, 0, tzinfo=_UTC)) == Decimal("21.0")
    assert rate_for(datetime(2026, 3, 1, 13, 30, tzinfo=_UTC)) == Decimal("-2.0")
    assert sc_for(date(2026, 3, 1)) == Decimal("45.0")
    # the merged rate map is returned for analytics
    assert rate_map[datetime(2026, 3, 1, 16, 0, tzinfo=_UTC)] == Decimal("21.0")


def test_agile_resolvers_merges_versions():
    """Two versions: their half-hourly rates merge into one instant-keyed
    lookup, and the daily standing charge is selected per version by date."""
    v1 = AgileVersion("AGILE-23-12-06", "Agile Dec 2023",
                      date(2023, 12, 6), date(2024, 10, 1))
    v2 = AgileVersion("AGILE-24-10-01", "Agile Oct 2024",
                      date(2024, 10, 1), None)

    class TwoVersionClient:
        def get_results(self, path, params=None):
            if "standing-charges" in path:
                value = 30.0 if "AGILE-23-12-06" in path else 45.0
                return [{"value_exc_vat": value, "valid_from": None, "valid_to": None}]
            # standard-unit-rates: each version serves a rate at a distinct instant
            if "AGILE-23-12-06" in path:
                return [{"value_exc_vat": 12.0,
                         "valid_from": "2024-01-15T00:00:00Z",
                         "valid_to": "2024-01-15T00:30:00Z"}]
            return [{"value_exc_vat": 25.0,
                     "valid_from": "2024-11-15T00:00:00Z",
                     "valid_to": "2024-11-15T00:30:00Z"}]

    rate_for, sc_for, rate_map = agile_resolvers(
        TwoVersionClient(), [v1, v2], "C", date(2024, 1, 1), date(2024, 12, 1))
    # rates from BOTH versions are present in the merged lookup AND the rate map
    assert rate_for(datetime(2024, 1, 15, 0, 0, tzinfo=_UTC)) == Decimal("12.0")
    assert rate_for(datetime(2024, 11, 15, 0, 0, tzinfo=_UTC)) == Decimal("25.0")
    assert rate_map[datetime(2024, 1, 15, 0, 0, tzinfo=_UTC)] == Decimal("12.0")
    assert rate_map[datetime(2024, 11, 15, 0, 0, tzinfo=_UTC)] == Decimal("25.0")
    # standing charge selected per version by date
    assert sc_for(date(2024, 1, 15)) == Decimal("30.0")
    assert sc_for(date(2024, 11, 15)) == Decimal("45.0")


def test_resolve_agile_versions_excludes_outgoing():
    """The AGILE- prefix also matches AGILE-OUTGOING-* (the export/Outgoing
    tariff), which must NOT be priced as an import tariff."""
    listing = AGILE_PRODUCTS_LIST + [
        {"code": "AGILE-OUTGOING-19-05-13", "full_name": "Agile Outgoing v1",
         "display_name": "Agile Outgoing",
         "available_from": "2018-01-01T00:00:00Z", "available_to": None},
    ]

    class ListClient:
        def get_results(self, path, params=None):
            assert path == "products/"
            return listing

    versions = resolve_agile_versions(ListClient(), date(2026, 1, 1), date(2026, 5, 31))
    codes = [v.product_code for v in versions]
    assert "AGILE-OUTGOING-19-05-13" not in codes
    assert codes == ["AGILE-24-10-01"]


def test_agile_resolvers_cover_period_to_boundary_instant():
    """The consumption endpoint includes a half-hour at exactly period_to (00:00
    of the --to date), but the rates endpoint is exclusive at period_to. The rate
    fetch must extend past period_to so that boundary instant has a covering rate."""
    boundary = datetime(2026, 5, 30, 0, 0, tzinfo=_UTC)

    class BoundaryAwareClient:
        def get_results(self, path, params=None):
            if "standing-charges" in path:
                return [{"value_exc_vat": 40.0, "valid_from": None, "valid_to": None}]
            # Honour period_to like the real rates API: only rates strictly before it.
            end = datetime.fromisoformat(params["period_to"].replace("Z", "+00:00"))
            rows = []
            for inst in (datetime(2026, 5, 29, 23, 30, tzinfo=_UTC), boundary):
                if inst < end:
                    rows.append({"value_exc_vat": 12.0, "valid_from": inst.isoformat(),
                                 "valid_to": inst.isoformat()})
            return rows

    v = AgileVersion("AGILE-24-10-01", "Agile Octopus", date(2024, 10, 1), None)
    rate_for, _sc, _map = agile_resolvers(
        BoundaryAwareClient(), [v], "C", date(2026, 5, 28), date(2026, 5, 30))
    assert rate_for(boundary) == Decimal("12.0")
