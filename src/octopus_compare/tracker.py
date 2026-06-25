from dataclasses import dataclass


@dataclass
class TrackerTariffs:
    elec_product: str
    elec_tariff: str
    gas_product: str
    gas_tariff: str


def resolve_current_tracker(client, region: str, available_at: str) -> TrackerTariffs:
    products = client.get_results(
        "products/", {"is_tracker": "true", "available_at": available_at}
    )
    trackers = [p for p in products if p.get("is_tracker")]
    if not trackers:
        raise ValueError("No current Tracker product found")
    code = trackers[0]["code"]
    detail = client.get(f"products/{code}/")
    elec = detail["single_register_electricity_tariffs"][region]["direct_debit_monthly"]["code"]
    gas = detail["single_register_gas_tariffs"][region]["direct_debit_monthly"]["code"]
    return TrackerTariffs(
        elec_product=code, elec_tariff=elec, gas_product=code, gas_tariff=gas
    )
