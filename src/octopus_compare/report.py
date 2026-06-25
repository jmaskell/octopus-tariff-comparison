import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from octopus_compare.costing import SupplyCost
from octopus_compare.tracker import TrackerVersion

_MONTHS = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _month_label(month: date, days: int) -> str:
    base = f"{_MONTHS[month.month]} {month.year}"
    return base if days >= 28 else f"{base} ({days} days)"


@dataclass
class MonthlyRow:
    month: date
    days: int
    flexible_pounds: Decimal
    tracker_pounds: Decimal

    @property
    def delta(self) -> Decimal:
        return self.tracker_pounds - self.flexible_pounds


@dataclass
class ComparisonResult:
    period_from: date
    period_to: date
    region: str
    tracker: TrackerVersion
    elec_flexible: SupplyCost
    elec_tracker: SupplyCost
    gas_flexible: SupplyCost
    gas_tracker: SupplyCost
    monthly: list

    @property
    def flexible_total(self) -> Decimal:
        return self.elec_flexible.total_pounds + self.gas_flexible.total_pounds

    @property
    def tracker_total(self) -> Decimal:
        return self.elec_tracker.total_pounds + self.gas_tracker.total_pounds

    @property
    def delta(self) -> Decimal:
        return self.tracker_total - self.flexible_total

    @property
    def pct(self) -> Decimal:
        if self.flexible_total == 0:
            return Decimal(0)
        return (self.delta / self.flexible_total * 100).quantize(Decimal("0.1"))


def recommend(result: ComparisonResult, threshold_pct: Decimal = Decimal("2")) -> str:
    if abs(result.pct) <= threshold_pct:
        return "MARGINAL"
    return "SWITCH BACK" if result.delta < 0 else "STAY"


def _block(label: str, flexible: SupplyCost, tracker: SupplyCost) -> list[str]:
    delta = tracker.total_pounds - flexible.total_pounds
    return [
        f"{label:<14}            Flexible      Tracker",
        f"  consumption          {flexible.consumption_kwh} kWh   {tracker.consumption_kwh} kWh",
        f"  energy (excl VAT)    £{flexible.energy_pounds}   £{tracker.energy_pounds}",
        f"  standing charge      £{flexible.standing_pounds}   £{tracker.standing_pounds}",
        f"  VAT (5%)             £{flexible.vat_pounds}   £{tracker.vat_pounds}",
        f"  total                £{flexible.total_pounds}   £{tracker.total_pounds}   £{delta:+}",
        "",
    ]


def format_text(result: ComparisonResult) -> str:
    t = result.tracker
    lines = [
        f"Octopus Tariff Comparison · {result.period_from} – {result.period_to}",
        "Flexible vs Octopus Tracker, costed on your actual usage · "
        f"Region {result.region}",
        f"  Switch-now Tracker: {t.product_code} · \"{t.display_name}\" · "
        f"current since {t.available_from}",
        "  Earlier months use the Tracker version current that month.",
        "",
    ]
    lines += _block("Electricity", result.elec_flexible, result.elec_tracker)
    lines += _block("Gas", result.gas_flexible, result.gas_tracker)
    lines.append("By month (elec + gas)      Flexible      Tracker      Delta")
    for row in result.monthly:
        lines.append(
            f"  {_month_label(row.month, row.days):<22} "
            f"£{row.flexible_pounds}   £{row.tracker_pounds}   £{row.delta:+}"
        )
    lines.append(
        f"  {'Total':<22} £{result.flexible_total}   £{result.tracker_total}   "
        f"£{result.delta:+}"
    )
    lines.append("")
    rec = recommend(result)
    if rec == "SWITCH BACK":
        lines.append(
            f"→ SWITCH BACK to Tracker — over this period it would have cost "
            f"{abs(result.pct)}% (£{abs(result.delta)}) less than Flexible."
        )
    elif rec == "STAY":
        lines.append(
            f"→ STAY on Flexible — Tracker would have cost "
            f"{abs(result.pct)}% (£{abs(result.delta)}) more."
        )
    else:
        lines.append(f"→ MARGINAL ({result.pct}%, £{result.delta}) — your call.")
    lines.append(
        "Figures are API-derived estimates incl. VAT, not your exact bill; "
        "Tracker prices change daily, so past savings don't guarantee future ones."
    )
    return "\n".join(lines)


def _supply_json(flexible: SupplyCost, tracker: SupplyCost) -> dict:
    def one(c: SupplyCost) -> dict:
        return {
            "consumption_kwh": str(c.consumption_kwh),
            "energy": str(c.energy_pounds),
            "standing": str(c.standing_pounds),
            "vat": str(c.vat_pounds),
            "total": str(c.total_pounds),
        }
    return {"flexible": one(flexible), "tracker": one(tracker)}


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
            "electricity": _supply_json(result.elec_flexible, result.elec_tracker),
            "gas": _supply_json(result.gas_flexible, result.gas_tracker),
            "monthly": [
                {
                    "month": str(row.month),
                    "days": row.days,
                    "flexible": str(row.flexible_pounds),
                    "tracker": str(row.tracker_pounds),
                    "delta": str(row.delta),
                }
                for row in result.monthly
            ],
            "flexible_total": str(result.flexible_total),
            "tracker_total": str(result.tracker_total),
            "delta": str(result.delta),
            "pct": str(result.pct),
            "recommendation": recommend(result),
        },
        indent=2,
    )
