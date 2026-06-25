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


def _actual_resolvers(client, supply, meter, cfg):
    """Per-day actual rate + standing-charge resolvers.

    A comparison period can span a change of the household's own tariff (e.g.
    Tracker -> Flexible). We fetch each in-window agreement's rates and resolve
    per day against the agreement actually active that day, so straddling
    periods are priced correctly rather than all at the latest tariff.
    """
    window = agreements_in_window(meter.agreements, cfg.period_from, cfg.period_to)
    lookups = {}
    for agreement in window:
        product = product_code_from_tariff(agreement.tariff_code)
        lookups[agreement.tariff_code] = (
            fetch_rates(client, supply, product, agreement.tariff_code,
                        cfg.period_from, cfg.period_to),
            fetch_standing_charges(client, supply, product, agreement.tariff_code,
                                   cfg.period_from, cfg.period_to),
        )

    def agreement_for(day):
        active = [
            a for a in window
            if (a.valid_from or date.min) <= day < (a.valid_to or date.max)
        ]
        if not active:
            raise ValueError(f"No agreement covers {day} for {supply}")
        return max(active, key=lambda a: a.valid_from or date.min)

    def rate_for(day):
        return lookups[agreement_for(day).tariff_code][0].rate_for(day)

    def sc_for(day):
        return lookups[agreement_for(day).tariff_code][1].rate_for(day)

    return rate_for, sc_for


def _supply_costs(client, supply, meter, cfg):
    raw = fetch_daily(client, supply, meter.identifier, meter.serials,
                      cfg.period_from, cfg.period_to)
    kwh = to_kwh(raw, supply, cfg.gas_units, cfg.gas_calorific_value)

    actual_rate_for, actual_sc_for = _actual_resolvers(client, supply, meter, cfg)

    tracker = resolve_tracker(client, meter)
    tracker_rates = fetch_rates(client, supply, tracker.product_code, tracker.tariff_code,
                                cfg.period_from, cfg.period_to)
    tracker_sc = fetch_standing_charges(client, supply, tracker.product_code, tracker.tariff_code,
                                        cfg.period_from, cfg.period_to)

    cost_actual = supply_cost(kwh, actual_rate_for, actual_sc_for)
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
