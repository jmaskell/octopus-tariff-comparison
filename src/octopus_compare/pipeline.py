from octopus_compare.account import parse_account, region_letter, build_tariff_code
from octopus_compare.config import Config
from octopus_compare.consumption import fetch_daily, to_kwh, gas_unit_info
from octopus_compare.coverage import compare_coverage
from octopus_compare.costing import supply_cost, sum_supply_costs, month_slices
from octopus_compare.rates import fetch_rates, fetch_standing_charges
from octopus_compare.report import ComparisonResult, MonthlyRow
from octopus_compare.tracker import (
    resolve_flexible,
    tracker_versions_for_window,
    latest_tracker_version,
    tracker_resolvers,
    resolve_fixed,
    fixed_resolvers,
    _version_from_detail,
)


class PricingError(Exception):
    pass


def _flexible_resolvers(client, supply, flex, region, cfg):
    tariff = build_tariff_code(supply, flex.product_code, region)
    rates = fetch_rates(client, supply, flex.product_code, tariff,
                        cfg.period_from, cfg.period_to)
    sc = fetch_standing_charges(client, supply, flex.product_code, tariff,
                                cfg.period_from, cfg.period_to)
    return rates.rate_for, sc.rate_for


def _tracker_versions(client, supply, meter, cfg):
    if cfg.tracker_product:
        detail = client.get(f"products/{cfg.tracker_product}/")
        return [_version_from_detail(cfg.tracker_product, detail)]
    return tracker_versions_for_window(client, meter, cfg.period_from, cfg.period_to)


def _price_months(supply, kwh, resolvers_by_tariff):
    """resolvers_by_tariff: {name: (rate_for, sc_for)}.
    Returns {name: {first_of_month: (day_set, SupplyCost)}}."""
    out = {name: {} for name in resolvers_by_tariff}
    for month, sub in month_slices(kwh):
        days = set(sub)
        for name, (rate_for, sc_for) in resolvers_by_tariff.items():
            try:
                cost = supply_cost(sub, rate_for, sc_for)
            except KeyError as e:
                raise PricingError(
                    f"Couldn't price {supply} ({name}) for every day in the window: {e}. "
                    "Rates don't cover the full period — try a narrower window with --from/--to."
                ) from e
            out[name][month] = (days, cost)
    return out


def _supply_breakdown(client, supply, meter, cfg, fixed_product):
    flex = resolve_flexible(client, meter)
    region = cfg.region or region_letter(flex.tariff_code)

    raw = fetch_daily(client, supply, meter.identifier, meter.serials,
                      cfg.period_from, cfg.period_to)
    kwh = to_kwh(raw, supply, cfg.gas_units, cfg.gas_calorific_value)
    gas_units = (gas_unit_info(raw, cfg.gas_units, cfg.gas_calorific_value)
                 if supply == "gas" else None)

    versions = _tracker_versions(client, supply, meter, cfg)
    latest = latest_tracker_version(versions)

    try:
        fixed_rate_for, fixed_sc_for = fixed_resolvers(client, supply, fixed_product, region)
    except KeyError as e:
        raise PricingError(
            f"Couldn't read the 12M Fixed rate for {supply}: {e}. "
            "The fixed product may not publish a rate for its start date."
        ) from e

    resolvers = {
        "flexible": _flexible_resolvers(client, supply, flex, region, cfg),
        "tracker": tracker_resolvers(client, supply, versions, region,
                                     cfg.period_from, cfg.period_to),
        "fixed": (fixed_rate_for, fixed_sc_for),
    }
    months = _price_months(supply, kwh, resolvers)
    return (region, latest, versions, gas_units,
            months["flexible"], months["tracker"], months["fixed"])


def _month_total(em, gm, month):
    e = em.get(month, (set(), None))[1]
    g = gm.get(month, (set(), None))[1]
    return (e.total_pounds if e else 0) + (g.total_pounds if g else 0)


def _priced_days(month_map) -> set:
    out = set()
    for days, _cost in month_map.values():
        out |= days
    return out


def run_comparison(client, config: Config) -> ComparisonResult:
    info = parse_account(client.get(f"accounts/{config.account}/"))
    fixed_product = resolve_fixed(client, config.fixed_product)

    (e_region, e_latest, e_versions, _e_gas,
     e_flex, e_trk, e_fix) = _supply_breakdown(
        client, "electricity", info.electricity, config, fixed_product)
    (_g_region, _g_latest, _g_versions, g_gas,
     g_flex, g_trk, g_fix) = _supply_breakdown(
        client, "gas", info.gas, config, fixed_product)

    def agg(m):
        return sum_supply_costs([c for _, c in m.values()])

    months = sorted(set(e_flex) | set(g_flex))
    monthly = []
    for month in months:
        e_days, _ = e_flex.get(month, (set(), None))
        g_days, _ = g_flex.get(month, (set(), None))
        monthly.append(MonthlyRow(
            month=month, days=len(e_days | g_days),
            flexible_pounds=_month_total(e_flex, g_flex, month),
            tracker_pounds=_month_total(e_trk, g_trk, month)))

    coverage = compare_coverage(
        config.period_from, config.period_to,
        {"electricity": _priced_days(e_flex), "gas": _priced_days(g_flex)})

    return ComparisonResult(
        period_from=config.period_from, period_to=config.period_to,
        region=e_region, tracker=e_latest, tracker_versions=e_versions,
        fixed=fixed_product,
        elec_flexible=agg(e_flex), elec_tracker=agg(e_trk), elec_fixed=agg(e_fix),
        gas_flexible=agg(g_flex), gas_tracker=agg(g_trk), gas_fixed=agg(g_fix),
        monthly=monthly, coverage=coverage, gas_units=g_gas,
        allow_partial=config.allow_partial_data,
    )
