import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from octopus_compare.agile_breakdown import AgileBreakdown
from octopus_compare.agile_insight import AgileInsight
from octopus_compare.costing import SupplyCost
from octopus_compare.tracker import TrackerVersion, FixedProduct
from octopus_compare.verdict import Verdict, decide

_MONTHS = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

_NAMES = {"flexible": "Flexible", "tracker": "Tracker", "fixed": "12M Fixed"}


def _pct(part: Decimal, whole: Decimal) -> Decimal:
    if whole == 0:
        return Decimal(0)
    return (part / whole * 100).quantize(Decimal("0.1"))


@dataclass
class MonthlyRow:
    month: date
    days: int
    flexible_pounds: Decimal
    tracker_pounds: Decimal

    @property
    def verdict(self) -> Verdict:
        return decide(self.flexible_pounds, self.tracker_pounds)


@dataclass
class ComparisonResult:
    period_from: date
    period_to: date
    region: str
    tracker: TrackerVersion
    tracker_versions: list
    fixed: FixedProduct
    elec_flexible: SupplyCost
    elec_tracker: SupplyCost
    elec_fixed: SupplyCost
    gas_flexible: SupplyCost
    gas_tracker: SupplyCost
    gas_fixed: SupplyCost
    monthly: list
    coverage: object
    gas_units: object
    allow_partial: bool = False

    @property
    def flexible_total(self) -> Decimal:
        return self.elec_flexible.total_pounds + self.gas_flexible.total_pounds

    @property
    def tracker_total(self) -> Decimal:
        return self.elec_tracker.total_pounds + self.gas_tracker.total_pounds

    @property
    def fixed_total(self) -> Decimal:
        return self.elec_fixed.total_pounds + self.gas_fixed.total_pounds


def recommend(result: ComparisonResult) -> Verdict:
    """Backtest verdict: Flexible (status quo) vs Tracker, same time basis."""
    return decide(result.flexible_total, result.tracker_total)


def fixed_verdict(result: ComparisonResult) -> Verdict:
    """Forward check: today's Fixed rate on this usage vs the Flexible backtest."""
    return decide(result.flexible_total, result.fixed_total)


def verdict_suppressed(result: ComparisonResult) -> bool:
    if result.allow_partial:
        return False
    gas_ok = result.gas_units is None or result.gas_units.confident
    return not (result.coverage.complete and gas_ok)


def _coverage_lines(result: ComparisonResult) -> list[str]:
    parts = " · ".join(
        f"{s.supply} {s.priced_days}/{s.expected_days} days"
        for s in result.coverage.per_supply
    )
    lines = [f"Coverage:  {parts}"]
    for s in result.coverage.per_supply:
        if s.missing_months:
            months = ", ".join(f"{m:%b %Y}" for m in s.missing_months)
            lines.append(f"  ⚠ {s.supply}: missing days in {months}")
    for note in result.coverage.notes:
        lines.append(f"  ⚠ {note}")
    return lines


def _gas_units_line(result: ComparisonResult) -> str:
    gi = result.gas_units
    if gi is None:
        return "Gas units: n/a"
    if gi.resolved == "m3":
        how = f"×{gi.factor.quantize(Decimal('0.01'))} kWh/m³"
    else:
        how = "no conversion"
    src = gi.requested if gi.requested in ("m3", "kwh") else "auto-detected"
    flag = "" if gi.confident else "  ⚠ ambiguous — pass --gas-units to be sure"
    return f"Gas units: {gi.resolved} ({src}, {how}){flag}"


def _block2(label, flexible, tracker) -> list[str]:
    return [
        f"{label:<14}          Flexible      Tracker",
        f"  consumption        {flexible.consumption_kwh} kWh   {tracker.consumption_kwh} kWh",
        f"  energy (excl VAT)  £{flexible.energy_pounds}   £{tracker.energy_pounds}",
        f"  standing charge    £{flexible.standing_pounds}   £{tracker.standing_pounds}",
        f"  VAT (5%)           £{flexible.vat_pounds}   £{tracker.vat_pounds}",
        f"  total              £{flexible.total_pounds}   £{tracker.total_pounds}",
        "",
    ]


def _cell(value: Decimal, mark: bool) -> str:
    return f"£{value}" + (" ✓" if mark else "")


def _month_label(month: date, days: int) -> str:
    base = f"{_MONTHS[month.month]} {month.year}"
    return base if days >= 28 else f"{base} ({days} days)"


def _backtest_verdict_lines(result: ComparisonResult) -> list[str]:
    if verdict_suppressed(result):
        return ["→ NO RECOMMENDATION — data incomplete/ambiguous (see Coverage below); "
                "narrow the window with --from/--to or pass --allow-partial-data."]
    v = recommend(result)
    saving = result.flexible_total - result.tracker_total
    pct = _pct(abs(saving), result.flexible_total)
    if v == Verdict.STAY:
        return [f"→ STAY on Flexible — £{abs(saving)} ({pct}%) cheaper than Tracker "
                "over this period."]
    if v == Verdict.SWITCH:
        return [f"→ SWITCH to Tracker — £{saving} ({pct}%) cheaper than Flexible "
                "over this period (historical backtest)."]
    return ["→ Flexible and Tracker are effectively tied over this period "
            f"(within £{abs(saving)} / {pct}%) — decide on price stability, not the number."]


def _forward_lock_in_lines(result: ComparisonResult) -> list[str]:
    f = result.fixed
    delta = result.flexible_total - result.fixed_total  # >0 => fixed cheaper
    pct = _pct(abs(delta), result.flexible_total)
    sign = "−" if delta > 0 else "+"
    head = [
        f'  {f.product_code} · "{f.display_name}"',
        f"  12M Fixed on this usage:  £{result.fixed_total}   "
        f"(vs your £{result.flexible_total} Flexible backtest: {sign}£{abs(delta)}, {sign}{pct}%)",
        "  Note: today's locked rate applied flat — NOT what was offered during this period.",
    ]
    if verdict_suppressed(result):
        return head + ["  → NO RECOMMENDATION — data incomplete/ambiguous."]
    v = fixed_verdict(result)
    if v == Verdict.SWITCH:
        head.append("  → Locking Fixed now would have undercut Flexible here — but past ≠ future.")
    elif v == Verdict.STAY:
        head.append("  → Locking Fixed now would have cost more than Flexible here.")
    else:
        head.append("  → Fixed and Flexible are effectively tied here — but past ≠ future.")
    return head


def format_text(result: ComparisonResult) -> str:
    codes = ", ".join(v.product_code for v in result.tracker_versions)
    lines = [
        f"Octopus Tariff Comparison · {result.period_from} – {result.period_to} · Region {result.region}",
        "",
        "HISTORICAL BACKTEST — what you'd have paid (Flexible vs Tracker, same basis)",
        f"  Tracker — historical versions used: {codes}",
        "",
    ]
    lines += _block2("Electricity", result.elec_flexible, result.elec_tracker)
    lines += _block2("Gas", result.gas_flexible, result.gas_tracker)
    lines.append("By month (elec + gas)  Flexible        Tracker")
    show_ticks = not verdict_suppressed(result)
    for row in result.monthly:
        v = row.verdict
        flex_win = show_ticks and v == Verdict.STAY
        trk_win = show_ticks and v == Verdict.SWITCH
        lines.append(
            f"  {_month_label(row.month, row.days):<20} "
            f"{_cell(row.flexible_pounds, flex_win):<14} "
            f"{_cell(row.tracker_pounds, trk_win)}"
        )
    tv = recommend(result)
    lines.append(
        f"  {'Total':<20} "
        f"{_cell(result.flexible_total, show_ticks and tv == Verdict.STAY):<14} "
        f"{_cell(result.tracker_total, show_ticks and tv == Verdict.SWITCH)}"
    )
    lines.append("")
    lines += _backtest_verdict_lines(result)
    lines += [
        "",
        "FORWARD LOCK-IN CHECK — today's 12M Fixed rate on this usage (NOT a backtest)",
    ]
    lines += _forward_lock_in_lines(result)
    lines.append("")
    lines += _coverage_lines(result)
    lines.append(_gas_units_line(result))
    lines.append(
        "Figures are API-derived estimates incl. VAT, not your exact bill. Flexible/Tracker "
        "are historical; Fixed is today's rate on past usage. Past savings don't guarantee "
        "future ones."
    )
    return "\n".join(lines)


def _supply_json(flexible, tracker, fixed) -> dict:
    def one(c):
        return {
            "consumption_kwh": str(c.consumption_kwh),
            "energy": str(c.energy_pounds),
            "standing": str(c.standing_pounds),
            "vat": str(c.vat_pounds),
            "total": str(c.total_pounds),
        }
    return {"flexible": one(flexible), "tracker": one(tracker), "fixed": one(fixed)}


def _coverage_json(result: ComparisonResult) -> dict:
    return {
        "complete": result.coverage.complete,
        "per_supply": [
            {"supply": s.supply, "priced_days": s.priced_days,
             "expected_days": s.expected_days,
             "missing_months": [str(m) for m in s.missing_months]}
            for s in result.coverage.per_supply
        ],
        "notes": result.coverage.notes,
    }


def format_json(result: ComparisonResult) -> str:
    gi = result.gas_units
    suppressed = verdict_suppressed(result)
    backtest_reco = None if suppressed else recommend(result).value
    forward_verdict = None if suppressed else fixed_verdict(result).value
    return json.dumps(
        {
            "period_from": str(result.period_from),
            "period_to": str(result.period_to),
            "region": result.region,
            "tracker": {
                "product_code": result.tracker.product_code,
                "display_name": result.tracker.display_name,
                "available_from": str(result.tracker.available_from),
                "versions_used": [v.product_code for v in result.tracker_versions],
            },
            "fixed": {
                "product_code": result.fixed.product_code,
                "display_name": result.fixed.display_name,
                "available_from": str(result.fixed.available_from),
            },
            "electricity": _supply_json(result.elec_flexible, result.elec_tracker, result.elec_fixed),
            "gas": _supply_json(result.gas_flexible, result.gas_tracker, result.gas_fixed),
            "monthly": [
                {"month": str(row.month), "days": row.days,
                 "flexible": str(row.flexible_pounds), "tracker": str(row.tracker_pounds),
                 "verdict": row.verdict.value}
                for row in result.monthly
            ],
            "flexible_total": str(result.flexible_total),
            "tracker_total": str(result.tracker_total),
            "backtest": {"recommendation": backtest_reco},
            "forward_lock_in": {
                "fixed_total": str(result.fixed_total),
                "delta_vs_flexible_pounds": str(result.flexible_total - result.fixed_total),
                "delta_pct": str(_pct(abs(result.flexible_total - result.fixed_total),
                                      result.flexible_total)),
                "verdict": forward_verdict,
            },
            "verdict_suppressed": suppressed,
            "coverage": _coverage_json(result),
            "gas_units": (None if gi is None else
                          {"requested": gi.requested, "resolved": gi.resolved,
                           "confident": gi.confident,
                           "factor": (None if gi.factor is None else str(gi.factor))}),
        },
        indent=2,
    )


@dataclass
class AgileMonthlyRow:
    month: date
    days: int
    flexible_pounds: Decimal
    agile_pounds: Decimal

    @property
    def cheapest(self) -> str:
        return "flexible" if self.flexible_pounds <= self.agile_pounds else "agile"


@dataclass
class AgileResult:
    period_from: date
    period_to: date
    region: str
    agile_versions: list
    elec_flexible: SupplyCost
    elec_agile: SupplyCost
    monthly: list
    insight: AgileInsight
    breakdown: AgileBreakdown
    coverage: object
    allow_partial: bool = False

    @property
    def flexible_total(self) -> Decimal:
        return self.elec_flexible.total_pounds

    @property
    def agile_total(self) -> Decimal:
        return self.elec_agile.total_pounds


def recommend_agile(result: AgileResult) -> Verdict:
    return decide(result.flexible_total, result.agile_total)


def agile_verdict_suppressed(result: AgileResult) -> bool:
    if result.allow_partial:
        return False
    return not result.coverage.complete


def _agile_version_line(versions) -> str:
    primary = next((v for v in versions if v.available_to is None), None)
    if primary is None:
        primary = max(versions, key=lambda v: v.available_from)
    extra = len(versions) - 1
    suffix = (f" (+{extra} earlier version{'s' if extra != 1 else ''} across the window)"
              if extra else "")
    return f'  Agile versions used: {primary.product_code} "{primary.display_name}"{suffix}'


def _agile_block(flex: SupplyCost, agile: SupplyCost) -> list[str]:
    return [
        "Electricity              Flexible      Agile",
        f"  consumption          {flex.consumption_kwh} kWh   {agile.consumption_kwh} kWh",
        f"  energy (excl VAT)    £{flex.energy_pounds}   £{agile.energy_pounds}",
        f"  standing charge      £{flex.standing_pounds}   £{agile.standing_pounds}",
        f"  VAT (5%)             £{flex.vat_pounds}   £{agile.vat_pounds}",
        f"  total                £{flex.total_pounds}   £{agile.total_pounds}",
        "",
    ]


def _agile_insight_lines(ins: AgileInsight) -> list[str]:
    start, end = ins.peak_window
    band = f"{start.strftime('%H:%M')}–{end.strftime('%H:%M')}"
    return [
        "Time-of-use insight",
        f"  Effective unit price  {ins.flex_effective_p}p/kWh   {ins.agile_effective_p}p/kWh",
        f"  Peak ({band})    {ins.peak_pct}% of usage · Agile spend £{ins.peak_agile_pounds} "
        f"(Flexible £{ins.peak_flex_pounds})",
        f"  Cheapest ½-hour       {ins.cheapest.when:%Y-%m-%d %H:%M}  {ins.cheapest.rate_p}p/kWh  "
        f"({ins.cheapest.kwh} kWh, £{ins.cheapest.cost_pounds})",
        f"  Priciest ½-hour       {ins.priciest.when:%Y-%m-%d %H:%M}  {ins.priciest.rate_p}p/kWh  "
        f"({ins.priciest.kwh} kWh, £{ins.priciest.cost_pounds})",
        f"  Negative-price slots  {ins.negative_count} half-hours you'd have been paid to use",
        "",
    ]


def _agile_coverage_lines(result: AgileResult) -> list[str]:
    c = result.coverage
    lines = [f"Coverage:  daily {c.daily_days} days · half-hourly {c.hh_days} days "
             f"(flex {c.daily_kwh} kWh vs agile {c.hh_kwh} kWh)"]
    if c.missing_hh_days:
        sample = ", ".join(f"{d:%Y-%m-%d}" for d in c.missing_hh_days[:5])
        more = "" if len(c.missing_hh_days) <= 5 else f" (+{len(c.missing_hh_days) - 5} more)"
        lines.append(f"  ⚠ half-hourly missing on {len(c.missing_hh_days)} day(s): {sample}{more}")
    for note in c.notes:
        lines.append(f"  ⚠ {note}")
    return lines


def _agile_reco_lines(result: AgileResult) -> list[str]:
    if agile_verdict_suppressed(result):
        return ["→ NO RECOMMENDATION — half-hourly data incomplete (see Coverage); "
                "narrow the window with --from/--to or pass --allow-partial-data."]
    v = recommend_agile(result)
    saving = result.flexible_total - result.agile_total
    pct = _pct(abs(saving), result.flexible_total)
    if v == Verdict.STAY:
        return [f"→ STAY on Flexible — £{abs(saving)} ({pct}%) cheaper than Agile over this period."]
    if v == Verdict.SWITCH:
        return [f"→ SWITCH to Agile — £{saving} ({pct}%) cheaper than Flexible over this period."]
    return [f"→ Flexible and Agile are effectively tied (within £{abs(saving)} / {pct}%) "
            "— decide on how much load you can shift, not the number."]


def _signed_p(v: Decimal) -> str:
    return f"+{v}" if v > 0 else f"-{abs(v)}" if v < 0 else f"{v}"


def _signed_pounds(v: Decimal) -> str:
    return f"-£{abs(v)}" if v < 0 else f"£{v}"


def _agile_decomposition_lines(d, *, total_delta_pounds, standing_delta_pounds,
                               vat_delta_pounds) -> list[str]:
    header = ("Why Agile is cheaper" if total_delta_pounds > 0
              else "Why Agile is more expensive" if total_delta_pounds < 0
              else "Flexible vs Agile — no overall difference")
    struct = ("Agile cheaper on average" if d.structural_p > 0
              else "Agile dearer on average" if d.structural_p < 0
              else "Agile same on average")
    behav = ("you use at cheaper times" if d.behavioural_p > 0
             else "you use at dearer times" if d.behavioural_p < 0
             else "your timing is neutral")
    energy_delta = d.total_pounds
    return [
        f"{header} (driven by the total bill, incl. VAT & standing)",
        "  Energy-only price pattern (excl VAT & standing):",
        f"    Flexible flat rate                 {d.flex_p} p/kWh",
        f"    Agile if you used power evenly     {d.time_avg_p} p/kWh   (time-average)",
        f"    Agile on your actual usage         {d.load_p} p/kWh   (your load)",
        "    ──────────────────────────────────────────────",
        f"    Structural ({struct})  {_signed_p(d.structural_p)} p/kWh   {_signed_pounds(d.structural_pounds)}",
        f"    Behavioural ({behav})  {_signed_p(d.behavioural_p)} p/kWh   {_signed_pounds(d.behavioural_pounds)}",
        f"    Energy subtotal  {_signed_p(d.total_p)} p/kWh   {_signed_pounds(energy_delta)}",
        "  Reconciliation to the bill (Flexible − Agile):",
        f"    Energy {_signed_pounds(energy_delta)} + Standing {_signed_pounds(standing_delta_pounds)} "
        f"+ VAT {_signed_pounds(vat_delta_pounds)} = Total {_signed_pounds(total_delta_pounds)}",
        "",
    ]


def _agile_hour_lines(b) -> list[str]:
    lines = ["Hour-of-day (London)       usage   avg Agile"]
    for hb in b.by_hour:
        bar = "█" * min(40, round(hb.usage_pct / Decimal("0.5")))
        mark = "  cheap" if hb.marker == "cheap" else "  DEAR" if hb.marker == "dear" else ""
        lines.append(f"  {hb.hour:02d}:00  {hb.usage_pct:>5}%   {hb.avg_price_p:>5}p  {bar}{mark}")
    lines.append(f"  Usage in 6 cheapest hours: {b.cheapest6_usage_pct}% · "
                 f"6 dearest: {b.dearest6_usage_pct}%  (flat user: 25% / 25%)")
    lines.append("")
    return lines


def format_agile_text(result: AgileResult) -> str:
    lines = [
        f"Octopus Agile Comparison · {result.period_from} – {result.period_to} · "
        f"Region {result.region}  (electricity only)",
        "Your real half-hourly usage costed against Agile's published half-hourly "
        "rates — a pure what-if backtest.",
        _agile_version_line(result.agile_versions),
        "",
    ]
    lines += _agile_block(result.elec_flexible, result.elec_agile)
    lines.append("By month                 Flexible      Agile")
    show_ticks = not agile_verdict_suppressed(result)
    for row in result.monthly:
        c = row.cheapest
        lines.append(
            f"  {_month_label(row.month, row.days):<20} "
            f"{_cell(row.flexible_pounds, show_ticks and c == 'flexible'):<14}"
            f"{_cell(row.agile_pounds, show_ticks and c == 'agile')}"
        )
    v = recommend_agile(result)
    lines.append(
        f"  {'Total':<20} "
        f"{_cell(result.flexible_total, show_ticks and v == Verdict.STAY):<14}"
        f"{_cell(result.agile_total, show_ticks and v == Verdict.SWITCH)}"
    )
    lines.append("")
    lines += _agile_insight_lines(result.insight)
    flex, agile = result.elec_flexible, result.elec_agile
    lines += _agile_decomposition_lines(
        result.breakdown.decomposition,
        total_delta_pounds=flex.total_pounds - agile.total_pounds,
        standing_delta_pounds=flex.standing_pounds - agile.standing_pounds,
        vat_delta_pounds=flex.vat_pounds - agile.vat_pounds,
    )
    lines += _agile_hour_lines(result.breakdown)
    lines += _agile_reco_lines(result)
    lines.append("")
    lines += _agile_coverage_lines(result)
    lines.append("Figures are API-derived estimates incl. VAT, not your exact bill.")
    return "\n".join(lines)


def _agile_supply_json(c: SupplyCost) -> dict:
    return {
        "consumption_kwh": str(c.consumption_kwh),
        "energy": str(c.energy_pounds),
        "standing": str(c.standing_pounds),
        "vat": str(c.vat_pounds),
        "total": str(c.total_pounds),
    }


def _half_hour_json(stat) -> dict:
    return {
        "when": stat.when.strftime("%Y-%m-%d %H:%M"),
        "rate_p": str(stat.rate_p),
        "kwh": str(stat.kwh),
        "cost": str(stat.cost_pounds),
    }


def _agile_coverage_json(result: AgileResult) -> dict:
    c = result.coverage
    return {
        "daily_days": c.daily_days,
        "hh_days": c.hh_days,
        "missing_hh_days": [str(d) for d in c.missing_hh_days],
        "daily_kwh": str(c.daily_kwh),
        "hh_kwh": str(c.hh_kwh),
        "divergence_pct": str(c.divergence_pct),
        "notes": c.notes,
    }


def format_agile_json(result: AgileResult) -> str:
    ins = result.insight
    suppressed = agile_verdict_suppressed(result)
    reco = None if suppressed else recommend_agile(result).value
    return json.dumps(
        {
            "period_from": str(result.period_from),
            "period_to": str(result.period_to),
            "region": result.region,
            "agile_versions": [
                {"product_code": v.product_code, "display_name": v.display_name,
                 "available_from": str(v.available_from),
                 "available_to": str(v.available_to) if v.available_to else None}
                for v in result.agile_versions
            ],
            "electricity": {
                "flexible": _agile_supply_json(result.elec_flexible),
                "agile": _agile_supply_json(result.elec_agile),
            },
            "monthly": [
                {"month": str(r.month), "days": r.days,
                 "flexible": str(r.flexible_pounds), "agile": str(r.agile_pounds),
                 "cheapest": r.cheapest}
                for r in result.monthly
            ],
            "flexible_total": str(result.flexible_total),
            "agile_total": str(result.agile_total),
            "insight": {
                "agile_effective_p": str(ins.agile_effective_p),
                "flex_effective_p": str(ins.flex_effective_p),
                "peak_window": [ins.peak_window[0].strftime("%H:%M"),
                                ins.peak_window[1].strftime("%H:%M")],
                "peak_pct": str(ins.peak_pct),
                "peak_kwh": str(ins.peak_kwh),
                "offpeak_kwh": str(ins.offpeak_kwh),
                "peak_agile": str(ins.peak_agile_pounds),
                "peak_flex": str(ins.peak_flex_pounds),
                "cheapest_half_hour": _half_hour_json(ins.cheapest),
                "priciest_half_hour": _half_hour_json(ins.priciest),
                "negative_slots": ins.negative_count,
            },
            "breakdown": {
                "decomposition": {
                    "flex_p": str(result.breakdown.decomposition.flex_p),
                    "time_avg_p": str(result.breakdown.decomposition.time_avg_p),
                    "load_p": str(result.breakdown.decomposition.load_p),
                    "structural_p": str(result.breakdown.decomposition.structural_p),
                    "behavioural_p": str(result.breakdown.decomposition.behavioural_p),
                    "total_p": str(result.breakdown.decomposition.total_p),
                    "structural_pounds": str(result.breakdown.decomposition.structural_pounds),
                    "behavioural_pounds": str(result.breakdown.decomposition.behavioural_pounds),
                    "total_pounds": str(result.breakdown.decomposition.total_pounds),
                    "total_kwh": str(result.breakdown.decomposition.total_kwh),
                },
                "by_hour": [
                    {"hour": hb.hour, "usage_pct": str(hb.usage_pct),
                     "avg_price_p": str(hb.avg_price_p), "marker": hb.marker}
                    for hb in result.breakdown.by_hour
                ],
                "cheapest6_usage_pct": str(result.breakdown.cheapest6_usage_pct),
                "dearest6_usage_pct": str(result.breakdown.dearest6_usage_pct),
            },
            "recommendation": reco,
            "verdict_suppressed": suppressed,
            "coverage": _agile_coverage_json(result),
        },
        indent=2,
    )
