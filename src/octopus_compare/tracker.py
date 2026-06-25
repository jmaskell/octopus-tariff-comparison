from dataclasses import dataclass
from datetime import date

from octopus_compare.account import MeterPoint, product_code_from_tariff


@dataclass
class TrackerTariff:
    product_code: str
    tariff_code: str


def resolve_tracker(client, meter_point: MeterPoint) -> TrackerTariff:
    """Most recent Octopus Tracker tariff in this meter's agreement history.

    Octopus Tracker (product codename SILVER) is NOT in the public /products/
    list, so it cannot be found by listing. But every product the account has
    been on is reachable via GET /products/{code}/, which reports is_tracker,
    and a tracker tariff keeps publishing daily unit rates well beyond the
    agreement period. So we walk the meter's agreements newest-first and return
    the first whose product is a tracker, using the household's own
    region-specific tariff code for it.
    """
    is_tracker: dict[str, bool] = {}
    for agreement in sorted(
        meter_point.agreements,
        key=lambda a: a.valid_from or date.min,
        reverse=True,
    ):
        product = product_code_from_tariff(agreement.tariff_code)
        if product not in is_tracker:
            detail = client.get(f"products/{product}/")
            is_tracker[product] = bool(detail.get("is_tracker"))
        if is_tracker[product]:
            return TrackerTariff(
                product_code=product, tariff_code=agreement.tariff_code
            )
    raise ValueError("No Tracker tariff found in this account's agreement history")
