import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from octopus_compare.costing import SupplyCost


@dataclass
class ComparisonResult:
    period_from: date
    period_to: date
    elec_actual: SupplyCost
    elec_tracker: SupplyCost
    gas_actual: SupplyCost
    gas_tracker: SupplyCost

    @property
    def actual_total(self) -> Decimal:
        return self.elec_actual.total_pounds + self.gas_actual.total_pounds

    @property
    def tracker_total(self) -> Decimal:
        return self.elec_tracker.total_pounds + self.gas_tracker.total_pounds

    @property
    def delta(self) -> Decimal:
        return self.tracker_total - self.actual_total

    @property
    def pct(self) -> Decimal:
        if self.actual_total == 0:
            return Decimal(0)
        return (self.delta / self.actual_total * 100).quantize(Decimal("0.1"))


def recommend(result: ComparisonResult, threshold_pct: Decimal = Decimal("2")) -> str:
    if abs(result.pct) <= threshold_pct:
        return "MARGINAL"
    return "SWITCH BACK" if result.delta < 0 else "STAY"


def format_text(result: ComparisonResult) -> str:
    rec = recommend(result)
    lines = [
        f"Octopus Tariff Comparison  ·  {result.period_from} – {result.period_to}",
        "",
        f"Electricity   flexible £{result.elec_actual.total_pounds}"
        f"   tracker £{result.elec_tracker.total_pounds}",
        f"Gas           flexible £{result.gas_actual.total_pounds}"
        f"   tracker £{result.gas_tracker.total_pounds}",
        f"Total         flexible £{result.actual_total}"
        f"   tracker £{result.tracker_total}   ({result.delta:+})",
        "",
    ]
    if rec == "SWITCH BACK":
        lines.append(
            f"→ SWITCH BACK to Tracker — it would have cost "
            f"{abs(result.pct)}% (£{abs(result.delta)}) less over this period."
        )
    elif rec == "STAY":
        lines.append(
            f"→ STAY on Flexible — Tracker would have cost "
            f"{abs(result.pct)}% (£{abs(result.delta)}) more."
        )
    else:
        lines.append(
            f"→ MARGINAL ({result.pct}%, £{result.delta}) — your call."
        )
    lines.append(
        "Figures are API-derived estimates incl. VAT, not your exact bill; "
        "Tracker prices change daily, so past savings don't guarantee future ones."
    )
    return "\n".join(lines)


def format_json(result: ComparisonResult) -> str:
    return json.dumps(
        {
            "period_from": str(result.period_from),
            "period_to": str(result.period_to),
            "actual_total": str(result.actual_total),
            "tracker_total": str(result.tracker_total),
            "delta": str(result.delta),
            "pct": str(result.pct),
            "recommendation": recommend(result),
        },
        indent=2,
    )
