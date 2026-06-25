from datetime import date

import pytest

from octopus_compare.account import MeterPoint, Agreement
from octopus_compare.client import ApiError
from octopus_compare.tracker import (
    discover_chain, _next_code, TrackerVersion,
    tracker_versions_for_window, latest_tracker_version)
from tests.fixtures.api_samples import TRACKER_PRODUCTS


class ProductClient:
    """Serves product details from TRACKER_PRODUCTS; 404s anything else."""

    def __init__(self, products=TRACKER_PRODUCTS, missing=()):
        self._products = products
        self._missing = set(missing)

    def get(self, path, params=None):
        code = path.split("/")[1]
        if code in self._missing or code not in self._products:
            raise ApiError(f"GET {path} failed: HTTP 404")
        return self._products[code]


def test_next_code_from_available_to():
    assert _next_code("SILVER-25-04-15", date(2025, 9, 2)) == "SILVER-25-09-02"
    assert _next_code("SILVER-25-09-02", date(2026, 4, 1)) == "SILVER-26-04-01"


def test_discover_chain_walks_to_latest():
    chain = discover_chain(ProductClient(), "SILVER-25-04-15")
    assert [v.product_code for v in chain] == [
        "SILVER-25-04-15", "SILVER-25-09-02", "SILVER-26-04-01"]
    latest = chain[-1]
    assert latest.available_to is None
    assert latest.display_name == "Octopus Tracker April 2026 v1"
    assert latest.available_from == date(2026, 4, 1)


def test_discover_chain_seed_is_latest():
    chain = discover_chain(ProductClient(), "SILVER-26-04-01")
    assert [v.product_code for v in chain] == ["SILVER-26-04-01"]


def test_discover_chain_stops_on_404():
    chain = discover_chain(ProductClient(missing=["SILVER-26-04-01"]), "SILVER-25-09-02")
    assert [v.product_code for v in chain] == ["SILVER-25-09-02"]


def _tracker_meter(tracker_codes):
    agreements = [
        Agreement(f"E-1R-{c}-C", date(2025, 1, 1), date(2026, 4, 1)) for c in tracker_codes
    ] + [Agreement("E-1R-VAR-22-11-01-C", date(2026, 4, 1), None)]
    return MeterPoint("mpan", ["s"], agreements)


class WindowClient(ProductClient):
    def get(self, path, params=None):
        code = path.split("/")[1]
        if code == "VAR-22-11-01":
            return {"is_tracker": False}
        return super().get(path, params)


def test_window_versions_history_anchor_plus_chain():
    # On the Sep-2025 version; window spans into the Apr-2026 era.
    meter = _tracker_meter(["SILVER-25-09-02"])
    versions = tracker_versions_for_window(
        WindowClient(), meter, date(2026, 1, 1), date(2026, 5, 1))
    assert [v.product_code for v in versions] == ["SILVER-25-09-02", "SILVER-26-04-01"]
    assert latest_tracker_version(versions).product_code == "SILVER-26-04-01"


def test_window_versions_includes_older_anchor():
    # History has an older version too; window starts in its era.
    meter = _tracker_meter(["SILVER-25-04-15", "SILVER-25-09-02"])
    versions = tracker_versions_for_window(
        WindowClient(), meter, date(2025, 5, 1), date(2025, 10, 1))
    assert [v.product_code for v in versions] == ["SILVER-25-04-15", "SILVER-25-09-02"]


def test_window_versions_no_tracker_raises():
    meter = MeterPoint("mpan", ["s"], [Agreement("E-1R-VAR-22-11-01-C", date(2026, 4, 1), None)])
    with pytest.raises(ValueError):
        tracker_versions_for_window(WindowClient(), meter, date(2026, 1, 1), date(2026, 5, 1))
