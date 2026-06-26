from datetime import date
from decimal import Decimal
from zoneinfo import ZoneInfo

from octopus_compare.account import parse_account, region_letter, build_tariff_code
from octopus_compare.agile import resolve_agile_versions, agile_resolvers
from octopus_compare.agile_costing import agile_supply_cost
from octopus_compare.agile_insight import compute_insight
from octopus_compare.config import Config
from octopus_compare.consumption import fetch_daily, fetch_halfhourly
from octopus_compare.costing import supply_cost, month_slices, sum_supply_costs
from octopus_compare.pipeline import PricingError
from octopus_compare.rates import fetch_rates, fetch_standing_charges
from octopus_compare.report import AgileResult, AgileMonthlyRow
from octopus_compare.tracker import resolve_flexible

_LONDON = ZoneInfo("Europe/London")


def _flex_resolvers(client, flex, region, cfg):
    tariff = build_tariff_code("electricity", flex.product_code, region)
    rates = fetch_rates(client, "electricity", flex.product_code, tariff,
                        cfg.period_from, cfg.period_to)
    sc = fetch_standing_charges(client, "electricity", flex.product_code, tariff,
                                cfg.period_from, cfg.period_to)
    return rates.rate_for, sc.rate_for


def _halfhourly_months(hh):
    """{first_of_month(local): {instant: kwh}}."""
    buckets: dict[date, dict] = {}
    for instant, kwh in hh.items():
        month = instant.astimezone(_LONDON).date().replace(day=1)
        buckets.setdefault(month, {})[instant] = kwh
    return buckets


def run_agile_comparison(client, config: Config) -> AgileResult:
    info = parse_account(client.get(f"accounts/{config.account}/"))
    meter = info.electricity
    flex = resolve_flexible(client, meter)
    region = config.region or region_letter(flex.tariff_code)

    daily = fetch_daily(client, "electricity", meter.identifier, meter.serials,
                        config.period_from, config.period_to)
    hh = fetch_halfhourly(client, meter.identifier, meter.serials,
                          config.period_from, config.period_to)
    if not hh:
        raise PricingError(
            "No half-hourly electricity data for this period — the Agile comparison "
            "needs half-hourly smart-meter readings. Try a different window with "
            "--from/--to, or check your meter is in half-hourly mode."
        )

    flex_rate_for, flex_sc_for = _flex_resolvers(client, flex, region, config)
    versions = resolve_agile_versions(client, config.period_from, config.period_to,
                                      config.agile_product)
    agile_rate_for, agile_sc_for = agile_resolvers(
        client, versions, region, config.period_from, config.period_to)

    flex_months = dict(month_slices(daily))
    agile_months = _halfhourly_months(hh)
    try:
        flex_costs = {m: supply_cost(sub, flex_rate_for, flex_sc_for)
                      for m, sub in flex_months.items()}
        agile_costs = {m: agile_supply_cost(sub, agile_rate_for, agile_sc_for)
                       for m, sub in agile_months.items()}
    except KeyError as e:
        raise PricingError(
            f"Couldn't price every half-hour on Agile: {e}. Rates don't cover the "
            "full period — try a narrower window with --from/--to."
        ) from e

    # Top-line totals aggregate the per-month costs (one rounding per month),
    # exactly as run_comparison's agg does — so the Flexible total matches the
    # main 3-column report to the penny and the monthly rows sum to the Total.
    elec_flex = sum_supply_costs(list(flex_costs.values()))
    elec_agile = sum_supply_costs(list(agile_costs.values()))

    monthly = []
    for month in sorted(set(flex_months) | set(agile_months)):
        f_cost = flex_costs.get(month)
        a_cost = agile_costs.get(month)
        days = len(set(flex_months.get(month, {}))
                   | {i.astimezone(_LONDON).date() for i in agile_months.get(month, {})})
        monthly.append(AgileMonthlyRow(
            month=month, days=days,
            flexible_pounds=f_cost.total_pounds if f_cost else Decimal(0),
            agile_pounds=a_cost.total_pounds if a_cost else Decimal(0)))

    insight = compute_insight(hh, agile_rate_for, flex_rate_for, config.peak_window)

    return AgileResult(
        period_from=config.period_from, period_to=config.period_to, region=region,
        agile_versions=versions,
        elec_flexible=elec_flex, elec_agile=elec_agile,
        monthly=monthly, insight=insight,
    )
