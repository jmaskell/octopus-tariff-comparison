from datetime import date

from octopus_compare.account import (
    parse_account, agreements_in_window, product_code_from_tariff,
)
from octopus_compare.config import Config
from octopus_compare.consumption import fetch_daily, to_kwh
from octopus_compare.costing import supply_cost
from octopus_compare.rates import fetch_rates, fetch_standing_charges
from octopus_compare.report import ComparisonResult
from octopus_compare.tracker import resolve_current_tracker


def _iso(d: date) -> str:
    return d.strftime("%Y-%m-%dT00:00:00Z")


def _supply_costs(client, supply, meter, tracker_product, tracker_tariff, cfg):
    raw = fetch_daily(client, supply, meter.identifier, meter.serial,
                      cfg.period_from, cfg.period_to)
    kwh = to_kwh(raw, supply, cfg.gas_units, cfg.gas_calorific_value)

    window = agreements_in_window(meter.agreements, cfg.period_from, cfg.period_to)
    actual = max(window, key=lambda a: a.valid_from or date.min)
    actual_product = product_code_from_tariff(actual.tariff_code)
    actual_rates = fetch_rates(client, supply, actual_product, actual.tariff_code,
                               cfg.period_from, cfg.period_to)
    actual_sc = fetch_standing_charges(client, supply, actual_product, actual.tariff_code,
                                       cfg.period_from, cfg.period_to)
    tracker_rates = fetch_rates(client, supply, tracker_product, tracker_tariff,
                                cfg.period_from, cfg.period_to)
    tracker_sc = fetch_standing_charges(client, supply, tracker_product, tracker_tariff,
                                        cfg.period_from, cfg.period_to)

    cost_actual = supply_cost(kwh, actual_rates.rate_for, actual_sc.rate_for)
    cost_tracker = supply_cost(kwh, tracker_rates.rate_for, tracker_sc.rate_for)
    return cost_actual, cost_tracker


def run_comparison(client, config: Config) -> ComparisonResult:
    info = parse_account(client.get(f"accounts/{config.account}/"))
    region = client.get(f"electricity-meter-points/{info.electricity.identifier}/")["gsp"]
    tracker = resolve_current_tracker(client, region, _iso(config.period_to))

    elec_actual, elec_tracker = _supply_costs(
        client, "electricity", info.electricity,
        tracker.elec_product, tracker.elec_tariff, config)
    gas_actual, gas_tracker = _supply_costs(
        client, "gas", info.gas,
        tracker.gas_product, tracker.gas_tariff, config)

    return ComparisonResult(
        period_from=config.period_from, period_to=config.period_to,
        elec_actual=elec_actual, elec_tracker=elec_tracker,
        gas_actual=gas_actual, gas_tracker=gas_tracker,
    )
