import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from octopus_compare.costing import SupplyCost
from octopus_compare.tracker import TrackerVersion, FixedProduct

_MONTHS = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

_NAMES = {"flexible": "Flexible", "tracker": "Tracker", "fixed": "12M Fixed"}


def _month_label(month: date, days: int) -> str:
    base = f"{_MONTHS[month.month]} {month.year}"
    return base if days >= 28 else f"{base} ({days} days)"


def _cheapest(flexible: Decimal, tracker: Decimal, fixed: Decimal) -> str:
    # min returns the first minimum -> tie-break order flexible, tracker, fixed.
    return min(
        [("flexible", flexible), ("tracker", tracker), ("fixed", fixed)],
        key=lambda p: p[1],
    )[0]


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
    fixed_pounds: Decimal

    @property
    def cheapest(self) -> str:
        return _cheapest(self.flexible_pounds, self.tracker_pounds, self.fixed_pounds)


@dataclass
class ComparisonResult:
    period_from: date
    period_to: date
    region: str
    tracker: TrackerVersion
    fixed: FixedProduct
    elec_flexible: SupplyCost
    elec_tracker: SupplyCost
    elec_fixed: SupplyCost
    gas_flexible: SupplyCost
    gas_tracker: SupplyCost
    gas_fixed: SupplyCost
    monthly: list

    @property
    def flexible_total(self) -> Decimal:
        return self.elec_flexible.total_pounds + self.gas_flexible.total_pounds

    @property
    def tracker_total(self) -> Decimal:
        return self.elec_tracker.total_pounds + self.gas_tracker.total_pounds

    @property
    def fixed_total(self) -> Decimal:
        return self.elec_fixed.total_pounds + self.gas_fixed.total_pounds

    @property
    def cheapest(self) -> str:
        return _cheapest(self.flexible_total, self.tracker_total, self.fixed_total)


def recommend(result: ComparisonResult, threshold_pct: Decimal = Decimal("2")) -> str:
    cheapest = result.cheapest
    if cheapest == "flexible":
        return "STAY"
    best = {"tracker": result.tracker_total, "fixed": result.fixed_total}[cheapest]
    saving_pct = _pct(result.flexible_total - best, result.flexible_total)
    return "MARGINAL" if saving_pct <= threshold_pct else "SWITCH"


def _block(label, flexible, tracker, fixed) -> list[str]:
    return [
        f"{label:<14}          Flexible      Tracker        Fixed",
        f"  consumption        {flexible.consumption_kwh} kWh   {tracker.consumption_kwh} kWh   {fixed.consumption_kwh} kWh",
        f"  energy (excl VAT)  £{flexible.energy_pounds}   £{tracker.energy_pounds}   £{fixed.energy_pounds}",
        f"  standing charge    £{flexible.standing_pounds}   £{tracker.standing_pounds}   £{fixed.standing_pounds}",
        f"  VAT (5%)           £{flexible.vat_pounds}   £{tracker.vat_pounds}   £{fixed.vat_pounds}",
        f"  total              £{flexible.total_pounds}   £{tracker.total_pounds}   £{fixed.total_pounds}",
        "",
    ]


def _cell(value: Decimal, mark: bool) -> str:
    return f"£{value}" + (" ✓" if mark else "")


def _recommendation_lines(result: ComparisonResult) -> list[str]:
    cheapest = result.cheapest
    if cheapest == "flexible":
        return ["→ STAY on Flexible — cheapest over this period."]
    totals = {"tracker": result.tracker_total, "fixed": result.fixed_total}
    best = totals[cheapest]
    saving = result.flexible_total - best
    pct = _pct(saving, result.flexible_total)
    name = _NAMES[cheapest].upper()
    if recommend(result) == "MARGINAL":
        head = (f"→ Cheapest over this period: {name} — £{best}, but only {pct}% "
                f"(£{saving}) under Flexible — MARGINAL, your call.")
    else:
        head = (f"→ Cheapest over this period: {name} — £{best}, {pct}% "
                f"(£{saving}) less than Flexible.")
    runner = "fixed" if cheapest == "tracker" else "tracker"
    ru_saving = result.flexible_total - totals[runner]
    ru_pct = _pct(abs(ru_saving), result.flexible_total)
    verb = "save" if ru_saving > 0 else "cost"
    return [head, f"  ({_NAMES[runner]} would {verb} {ru_pct}% / £{abs(ru_saving)} vs Flexible.)"]


def format_text(result: ComparisonResult) -> str:
    t, f = result.tracker, result.fixed
    lines = [
        f"Octopus Tariff Comparison · {result.period_from} – {result.period_to} · Region {result.region}",
        "Flexible, Tracker and 12M Fixed, costed on your actual usage — all pure what-ifs:",
        f"  Tracker (switch-now): {t.product_code} · \"{t.display_name}\" · current since {t.available_from}",
        f"  Fixed (12M lock-in):  {f.product_code} · \"{f.display_name}\" · today's locked rate, flat",
        "",
    ]
    lines += _block("Electricity", result.elec_flexible, result.elec_tracker, result.elec_fixed)
    lines += _block("Gas", result.gas_flexible, result.gas_tracker, result.gas_fixed)
    lines.append("By month (elec + gas)  Flexible        Tracker         Fixed")
    for row in result.monthly:
        c = row.cheapest
        lines.append(
            f"  {_month_label(row.month, row.days):<20} "
            f"{_cell(row.flexible_pounds, c == 'flexible'):<14} "
            f"{_cell(row.tracker_pounds, c == 'tracker'):<14} "
            f"{_cell(row.fixed_pounds, c == 'fixed')}"
        )
    c = result.cheapest
    lines.append(
        f"  {'Total':<20} "
        f"{_cell(result.flexible_total, c == 'flexible'):<14} "
        f"{_cell(result.tracker_total, c == 'tracker'):<14} "
        f"{_cell(result.fixed_total, c == 'fixed')}"
    )
    lines.append("")
    lines += _recommendation_lines(result)
    lines.append(
        "Figures are API-derived estimates incl. VAT, not your exact bill; Tracker prices "
        "change daily and fixed/tracker rates change between sign-ups, so past savings "
        "don't guarantee future ones."
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


def format_json(result: ComparisonResult) -> str:
    return json.dumps(
        {
            "period_from": str(result.period_from),
            "period_to": str(result.period_to),
            "region": result.region,
            "tracker": {
                "product_code": result.tracker.product_code,
                "display_name": result.tracker.display_name,
                "available_from": str(result.tracker.available_from),
            },
            "fixed": {
                "product_code": result.fixed.product_code,
                "display_name": result.fixed.display_name,
                "available_from": str(result.fixed.available_from),
            },
            "electricity": _supply_json(result.elec_flexible, result.elec_tracker, result.elec_fixed),
            "gas": _supply_json(result.gas_flexible, result.gas_tracker, result.gas_fixed),
            "monthly": [
                {
                    "month": str(row.month),
                    "days": row.days,
                    "flexible": str(row.flexible_pounds),
                    "tracker": str(row.tracker_pounds),
                    "fixed": str(row.fixed_pounds),
                    "cheapest": row.cheapest,
                }
                for row in result.monthly
            ],
            "flexible_total": str(result.flexible_total),
            "tracker_total": str(result.tracker_total),
            "fixed_total": str(result.fixed_total),
            "cheapest": result.cheapest,
            "recommendation": recommend(result),
        },
        indent=2,
    )
