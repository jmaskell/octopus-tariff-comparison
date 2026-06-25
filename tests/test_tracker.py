from datetime import date

import pytest

from octopus_compare.account import MeterPoint, Agreement
from octopus_compare.tracker import resolve_tracker, TrackerTariff


class FakeClient:
    def __init__(self, is_tracker_by_product):
        self._is_tracker = is_tracker_by_product
        self.detail_calls = []

    def get(self, path, params=None):
        code = path.split("/")[1]  # "products/SILVER-24-12-31/" -> "SILVER-24-12-31"
        self.detail_calls.append(code)
        return {"is_tracker": self._is_tracker.get(code, False)}


def _meter():
    return MeterPoint(
        identifier="1200033187430",
        serial="19L3474725",
        agreements=[
            Agreement("E-1R-SILVER-24-12-31-C", date(2025, 8, 19), date(2026, 3, 24)),
            Agreement("E-1R-VAR-22-11-01-C", date(2026, 3, 24), None),
        ],
    )


def test_resolves_most_recent_tracker_agreement():
    client = FakeClient({"SILVER-24-12-31": True, "VAR-22-11-01": False})
    result = resolve_tracker(client, _meter())
    assert result == TrackerTariff(
        product_code="SILVER-24-12-31", tariff_code="E-1R-SILVER-24-12-31-C"
    )
    # newest-first: current Flexible (VAR) is checked before the SILVER tracker
    assert client.detail_calls == ["VAR-22-11-01", "SILVER-24-12-31"]


def test_raises_when_no_tracker_in_history():
    client = FakeClient({"VAR-22-11-01": False})
    meter = MeterPoint(
        "m", "s", [Agreement("E-1R-VAR-22-11-01-C", date(2026, 3, 24), None)]
    )
    with pytest.raises(ValueError):
        resolve_tracker(client, meter)
