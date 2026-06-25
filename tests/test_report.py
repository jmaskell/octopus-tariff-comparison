from datetime import date
from decimal import Decimal

from octopus_compare.costing import SupplyCost
from octopus_compare.report import ComparisonResult, recommend, format_text, format_json


def _cost(total):
    t = Decimal(total)
    return SupplyCost(Decimal(0), t, Decimal(0), t, Decimal(0), t)


def _result(actual, tracker):
    return ComparisonResult(
        period_from=date(2026, 3, 1), period_to=date(2026, 5, 31),
        elec_actual=_cost(actual), elec_tracker=_cost(tracker),
        gas_actual=_cost(0), gas_tracker=_cost(0),
    )


def test_totals_and_delta():
    r = _result("553.45", "473.70")
    assert r.actual_total == Decimal("553.45")
    assert r.tracker_total == Decimal("473.70")
    assert r.delta == Decimal("-79.75")


def test_recommend_switch_when_tracker_cheaper():
    assert recommend(_result("553.45", "473.70")) == "SWITCH BACK"


def test_recommend_stay_when_tracker_dearer():
    assert recommend(_result("473.70", "553.45")) == "STAY"


def test_recommend_marginal_within_threshold():
    assert recommend(_result("100.00", "101.00")) == "MARGINAL"


def test_format_text_mentions_recommendation():
    text = format_text(_result("553.45", "473.70"))
    assert "SWITCH BACK" in text


def test_format_json_roundtrips():
    import json
    data = json.loads(format_json(_result("553.45", "473.70")))
    assert data["recommendation"] == "SWITCH BACK"
    assert data["actual_total"] == "553.45"
