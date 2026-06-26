from datetime import date
from decimal import Decimal

import pytest

from octopus_compare.tracker import resolve_fixed, FixedProduct

FIXED_LIST = [
    {"code": "OE-FIX-12M-26-06-24", "full_name": "Octopus 12M Fixed June 2026 v5",
     "display_name": "Octopus 12M Fixed",
     "available_from": "2026-06-24T00:00:00+01:00", "available_to": None},
    {"code": "OE-FIX-12M-26-01-10", "full_name": "Octopus 12M Fixed January 2026 v3",
     "display_name": "Octopus 12M Fixed",
     "available_from": "2026-01-10T00:00:00Z", "available_to": "2026-06-24T00:00:00+01:00"},
    {"code": "COSY-FIX-12M-26-06-25", "full_name": "Cosy Octopus 12M Fixed",
     "display_name": "Cosy", "available_from": "2026-06-25T00:00:00+01:00", "available_to": None},
]


class ListClient:
    def __init__(self, results=FIXED_LIST):
        self._results = results

    def get_results(self, path, params=None):
        assert path == "products/"
        return self._results

    def get(self, path, params=None):
        code = path.split("/")[1]
        for r in FIXED_LIST:
            if r["code"] == code:
                return r
        raise AssertionError(code)


def test_resolve_fixed_picks_current_oe_fix_12m():
    fp = resolve_fixed(ListClient())
    assert fp.product_code == "OE-FIX-12M-26-06-24"
    assert fp.display_name == "Octopus 12M Fixed June 2026 v5"
    assert fp.available_from == date(2026, 6, 24)


def test_resolve_fixed_override():
    fp = resolve_fixed(ListClient(), "OE-FIX-12M-26-01-10")
    assert fp.product_code == "OE-FIX-12M-26-01-10"
    assert fp.available_from == date(2026, 1, 10)


def test_resolve_fixed_none_found_raises():
    only_cosy = [r for r in FIXED_LIST if r["code"].startswith("COSY")]
    with pytest.raises(ValueError):
        resolve_fixed(ListClient(only_cosy))
