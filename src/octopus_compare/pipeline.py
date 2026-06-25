from datetime import date

from octopus_compare.account import (
    parse_account,
    agreements_in_window,
    product_code_from_tariff,
)
from octopus_compare.config import Config
from octopus_compare.consumption import fetch_daily, to_kwh
from octopus_compare.costing import supply_cost
from octopus_compare.rates import fetch_rates, fetch_standing_charges
from octopus_compare.report import ComparisonResult
from octopus_compare.tracker import resolve_tracker


def _supply_costs(client, supply, meter, cfg):
    raw = fetch_daily(client, supply, meter.identifier, meter.serial,
                      cfg.period_from, cfg.period_to)
    kwh = to_kwh(raw, supply, cfg.gas_units, cfg.gas_calorific_value)

    # Actual: the agreement active at the end of the window (the current tariff).
    window = agreements_in_window(meter.agreements, cfg.period_from, cfg.period_to)
    actual = max(window, key=lambda a: a.valid_from or date.min)
    actual_product = product_code_from_tariff(actual.tariff_code)
    actual_rates = fetch_rates(client, supply, actual_product, actual.tariff_code,
                               cfg.period_from, cfg.period_to)
    actual_sc = fetch_standing_charges(client, supply, actual_product, actual.tariff_code,
                                       cfg.period_from, cfg.period_to)

    # Tracker: the most recent Tracker tariff from this meter's agreement history.
    tracker = resolve_tracker(client, meter)
    tracker_rates = fetch_rates(client, supply, tracker.product_code, tracker.tariff_code,
                                cfg.period_from, cfg.period_to)
    tracker_sc = fetch_standing_charges(client, supply, tracker.product_code, tracker.tariff_code,
                                        cfg.period_from, cfg.period_to)

    cost_actual = supply_cost(kwh, actual_rates.rate_for, actual_sc.rate_for)
    cost_tracker = supply_cost(kwh, tracker_rates.rate_for, tracker_sc.rate_for)
    return cost_actual, cost_tracker


def run_comparison(client, config: Config) -> ComparisonResult:
    info = parse_account(client.get(f"accounts/{config.account}/"))
    elec_actual, elec_tracker = _supply_costs(client, "electricity", info.electricity, config)
    gas_actual, gas_tracker = _supply_costs(client, "gas", info.gas, config)
    return ComparisonResult(
        period_from=config.period_from, period_to=config.period_to,
        elec_actual=elec_actual, elec_tracker=elec_tracker,
        gas_actual=gas_actual, gas_tracker=gas_tracker,
    )
