from octopus_compare.account import parse_account, region_letter, build_tariff_code
from octopus_compare.config import Config
from octopus_compare.consumption import fetch_daily, to_kwh
from octopus_compare.costing import supply_cost, sum_supply_costs, month_slices
from octopus_compare.rates import fetch_rates, fetch_standing_charges
from octopus_compare.report import ComparisonResult, MonthlyRow
from octopus_compare.tracker import (
    resolve_flexible,
    tracker_versions_for_window,
    latest_tracker_version,
    tracker_resolvers,
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


def _supply_breakdown(client, supply, meter, cfg):
    """Return (region, latest_tracker_version, flex_months, trk_months) where the
    *_months are {first_of_month: (day_set, SupplyCost)}."""
    flex = resolve_flexible(client, meter)
    region = cfg.region or region_letter(flex.tariff_code)

    raw = fetch_daily(client, supply, meter.identifier, meter.serials,
                      cfg.period_from, cfg.period_to)
    kwh = to_kwh(raw, supply, cfg.gas_units, cfg.gas_calorific_value)

    flex_rate_for, flex_sc_for = _flexible_resolvers(client, supply, flex, region, cfg)
    versions = _tracker_versions(client, supply, meter, cfg)
    latest = latest_tracker_version(versions)
    trk_rate_for, trk_sc_for = tracker_resolvers(
        client, supply, versions, region, cfg.period_from, cfg.period_to)

    flex_months = {}
    trk_months = {}
    for month, sub in month_slices(kwh):
        days = set(sub)
        try:
            flex_cost = supply_cost(sub, flex_rate_for, flex_sc_for)
        except KeyError as e:
            raise PricingError(
                f"Couldn't price {supply} for every day in the window: {e}. "
                "Rates don't cover the full period — try a narrower window with --from/--to."
            ) from e
        try:
            trk_cost = supply_cost(sub, trk_rate_for, trk_sc_for)
        except KeyError as e:
            raise PricingError(
                f"Couldn't price {supply} for every day in the window: {e}. "
                "Rates don't cover the full period — try a narrower window with --from/--to."
            ) from e
        flex_months[month] = (days, flex_cost)
        trk_months[month] = (days, trk_cost)
    return region, latest, flex_months, trk_months


def run_comparison(client, config: Config) -> ComparisonResult:
    info = parse_account(client.get(f"accounts/{config.account}/"))

    e_region, e_latest, e_flex_m, e_trk_m = _supply_breakdown(
        client, "electricity", info.electricity, config)
    _g_region, _g_latest, g_flex_m, g_trk_m = _supply_breakdown(
        client, "gas", info.gas, config)

    elec_flexible = sum_supply_costs([c for _, c in e_flex_m.values()])
    elec_tracker = sum_supply_costs([c for _, c in e_trk_m.values()])
    gas_flexible = sum_supply_costs([c for _, c in g_flex_m.values()])
    gas_tracker = sum_supply_costs([c for _, c in g_trk_m.values()])

    months = sorted(set(e_flex_m) | set(g_flex_m))
    monthly = []
    for month in months:
        e_days, e_flex = e_flex_m.get(month, (set(), None))
        g_days, g_flex = g_flex_m.get(month, (set(), None))
        _e_days, e_trk = e_trk_m.get(month, (set(), None))
        _g_days, g_trk = g_trk_m.get(month, (set(), None))
        flex_pounds = (e_flex.total_pounds if e_flex else 0) + (g_flex.total_pounds if g_flex else 0)
        trk_pounds = (e_trk.total_pounds if e_trk else 0) + (g_trk.total_pounds if g_trk else 0)
        monthly.append(MonthlyRow(
            month=month, days=len(e_days | g_days),
            flexible_pounds=flex_pounds, tracker_pounds=trk_pounds))

    return ComparisonResult(
        period_from=config.period_from, period_to=config.period_to,
        region=e_region, tracker=e_latest,
        elec_flexible=elec_flexible, elec_tracker=elec_tracker,
        gas_flexible=gas_flexible, gas_tracker=gas_tracker,
        monthly=monthly,
    )
