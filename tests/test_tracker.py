from octopus_compare.tracker import resolve_current_tracker, TrackerTariffs
from tests.fixtures.api_samples import PRODUCTS_LIST, PRODUCT_DETAIL


class FakeClient:
    def get_results(self, path, params=None):
        assert path == "products/"
        assert params["is_tracker"] == "true"
        return PRODUCTS_LIST["results"]

    def get(self, path, params=None):
        assert path == "products/SILVER-26-06-01/"
        return PRODUCT_DETAIL


def test_resolve_current_tracker():
    t = resolve_current_tracker(FakeClient(), "_C", "2026-06-25T00:00:00Z")
    assert t == TrackerTariffs(
        elec_product="SILVER-26-06-01",
        elec_tariff="E-1R-SILVER-26-06-01-C",
        gas_product="SILVER-26-06-01",
        gas_tariff="G-1R-SILVER-26-06-01-C",
    )
