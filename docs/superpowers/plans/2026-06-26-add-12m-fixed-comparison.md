# Add Octopus 12M Fixed Column — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a third comparison column — **Octopus 12M Fixed** — alongside Flexible and Tracker, costed on the same real usage, with the cheapest of the three marked per month and a 3-way recommendation.

**Architecture:** The Fixed column reuses the existing slice-&-reuse machinery. The current fixed product (`OE-FIX-12M-*`, listed — no chain-walk) is resolved once; its locked rate is fetched and applied **flat** to every day via an all-covering lookup (so a past backtest window prices fine despite the product starting in the future). `pipeline.py` computes per-month Fixed `SupplyCost`s exactly like Flexible/Tracker; `report.py` renders a third column and a 3-way recommendation.

**Tech Stack:** Python 3, `requests`, `python-dotenv`, `pytest`, `Decimal`. No new dependencies.

## Global Constraints

- **Fixed product:** the standard **Octopus 12M Fixed**, code prefix `OE-FIX-12M-` (today `OE-FIX-12M-26-06-24`). Exclude Cosy/Go/Intelligent variants (`COSY-FIX-12M-`, `GO-FIX-12M-`, `INTELLI-FIX-12M-`). It is **listed** — resolve by `GET /v1/products/?brand=OCTOPUS_ENERGY` and filtering.
- **Fixed basis:** today's locked rate applied **flat** to every month (constant rate; only usage varies). Do NOT date-match the fixed product's rates against window days.
- **Layout:** three absolute columns (Flexible / Tracker / Fixed); mark the cheapest of the three per monthly row and on the Total with a trailing ` ✓`. Tie-break order: flexible, tracker, fixed.
- **Recommendation (3-way):** `best = min(flexible_total, tracker_total, fixed_total)`. Flexible cheapest → STAY. Else name the cheapest + saving vs Flexible; `MARGINAL` if that saving ≤ 2% of Flexible; else SWITCH. One runner-up note line.
- **Engine untouched:** do NOT modify `costing.py` (`supply_cost`, `daily_energy_pence`, `standing_pence`, `SupplyCost`). The bill evals in `tests/test_costing.py` must keep passing.
- **Money:** `Decimal` throughout; rates matched in exc-VAT pence; VAT per month via `supply_cost`.
- **Tariff code:** `{E|G}-1R-{product}-{region}`; region from the account's tariff codes (per supply), overridable via `--region`.
- **Tests:** pytest; inline `FakeClient` routing by `path`; shared fixtures in `tests/fixtures/api_samples.py`; run from repo root with `.venv/bin/python -m pytest`.
- **Commit after every task.**

## File Structure

- `src/octopus_compare/rates.py` (modify) — add `flat_lookup`.
- `src/octopus_compare/tracker.py` (modify) — add `FixedProduct`, `resolve_fixed`, `fixed_resolvers`. (Sibling of the existing product-resolution helpers; reuses `_to_date`, `build_tariff_code`, `fetch_rates`, `fetch_standing_charges`, `flat_lookup`.)
- `src/octopus_compare/config.py` (modify) — add `--fixed-product`.
- `src/octopus_compare/report.py` (rewrite) — third column, ✓ marker, 3-way recommend.
- `src/octopus_compare/pipeline.py` (rewrite) — resolve + price the Fixed column.
- Tests: new `tests/test_fixed.py`; additions to `tests/test_rates.py`, `tests/test_config.py`; rewrites of `tests/test_report.py`, `tests/test_pipeline.py`; fixtures in `tests/fixtures/api_samples.py`.

---

### Task 1: `flat_lookup` (`rates.py`)

**Files:**
- Modify: `src/octopus_compare/rates.py`
- Test: `tests/test_rates.py`

**Interfaces:**
- Consumes: existing `RateLookup`, `_Window`.
- Produces: `flat_lookup(value: Decimal) -> RateLookup` — a lookup whose `rate_for(day)` returns `value` for ANY day (one all-covering window).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_rates.py`:

```python
from octopus_compare.rates import flat_lookup


def test_flat_lookup_returns_value_for_any_day():
    lk = flat_lookup(Decimal("21.50"))
    assert lk.rate_for(date(2026, 1, 1)) == Decimal("21.50")
    assert lk.rate_for(date(2030, 12, 31)) == Decimal("21.50")
```

(`date` and `Decimal` are already imported at the top of `tests/test_rates.py`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_rates.py::test_flat_lookup_returns_value_for_any_day -v`
Expected: FAIL with `ImportError: cannot import name 'flat_lookup'`.

- [ ] **Step 3: Write minimal implementation**

Append to `src/octopus_compare/rates.py`:

```python
def flat_lookup(value: Decimal) -> RateLookup:
    """A RateLookup that returns the same value for every day (no date gating).
    Backs the 12M Fixed column, whose locked rate applies flat across the window."""
    return RateLookup([_Window(date.min, date.max, value)])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_rates.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/octopus_compare/rates.py tests/test_rates.py
git commit -m "feat: flat_lookup for the fixed tariff's constant rate"
```

---

### Task 2: `FixedProduct` + `resolve_fixed` (`tracker.py`)

**Files:**
- Modify: `src/octopus_compare/tracker.py`
- Test: `tests/test_fixed.py` (create)

**Interfaces:**
- Consumes: `_to_date` (existing in tracker.py), `client.get_results`, `client.get`.
- Produces:
  - `FixedProduct(product_code: str, display_name: str, available_from: date)` (dataclass).
  - `resolve_fixed(client, override: str | None = None) -> FixedProduct` — with `override`, fetch `products/{override}/`; otherwise list `products/?brand=OCTOPUS_ENERGY`, keep codes starting `OE-FIX-12M-`, pick `available_to is None` (else latest `available_from`). Raises `ValueError` if none.

- [ ] **Step 1: Write the failing test**

Create `tests/test_fixed.py`:

```python
from datetime import date
from decimal import Decimal

import pytest

from octopus_compare.tracker import resolve_fixed, fixed_resolvers, FixedProduct

FIXED_LIST = [
    {"code": "OE-FIX-12M-26-06-24", "full_name": "Octopus 12M Fixed June 2026 v5",
     "display_name": "Octopus 12M Fixed",
     "available_from": "2026-06-24T00:00:00+01:00", "available_to": None},
    {"code": "OE-FIX-12M-26-01-10", "full_name": "Octopus 12M Fixed January 2026 v3",
     "display_name": "Octopus 12M Fixed",
     "available_from": "2026-01-10T00:00:00Z", "available_to": "2026-06-24T00:00:00+01:00"},
    {"code": "COSY-FIX-12M-26-06-25", "full_name": "Cosy Octopus 12M Fixed",
     "display_name": "Cosy", "available_from": "2026-06-25T00:00:00+01:00", "available_to": None},
]


class ListClient:
    def __init__(self, results=FIXED_LIST):
        self._results = results

    def get_results(self, path, params=None):
        assert path == "products/"
        return self._results

    def get(self, path, params=None):
        code = path.split("/")[1]
        for r in FIXED_LIST:
            if r["code"] == code:
                return r
        raise AssertionError(code)


def test_resolve_fixed_picks_current_oe_fix_12m():
    fp = resolve_fixed(ListClient())
    assert fp.product_code == "OE-FIX-12M-26-06-24"
    assert fp.display_name == "Octopus 12M Fixed June 2026 v5"
    assert fp.available_from == date(2026, 6, 24)


def test_resolve_fixed_override():
    fp = resolve_fixed(ListClient(), "OE-FIX-12M-26-01-10")
    assert fp.product_code == "OE-FIX-12M-26-01-10"
    assert fp.available_from == date(2026, 1, 10)


def test_resolve_fixed_none_found_raises():
    only_cosy = [r for r in FIXED_LIST if r["code"].startswith("COSY")]
    with pytest.raises(ValueError):
        resolve_fixed(ListClient(only_cosy))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_fixed.py -v`
Expected: FAIL with `ImportError: cannot import name 'resolve_fixed'`.

- [ ] **Step 3: Write minimal implementation**

Append to `src/octopus_compare/tracker.py`:

```python
_FIXED_PREFIX = "OE-FIX-12M-"


@dataclass
class FixedProduct:
    product_code: str
    display_name: str
    available_from: date


def resolve_fixed(client, override: str | None = None) -> FixedProduct:
    if override:
        detail = client.get(f"products/{override}/")
        return FixedProduct(
            override,
            detail.get("full_name") or detail.get("display_name") or override,
            _to_date(detail.get("available_from")),
        )
    results = client.get_results("products/", {"brand": "OCTOPUS_ENERGY"})
    candidates = [r for r in results if r.get("code", "").startswith(_FIXED_PREFIX)]
    if not candidates:
        raise ValueError("No Octopus 12M Fixed product found in the product list")
    current = [r for r in candidates if not r.get("available_to")]
    pool = current or candidates
    best = max(pool, key=lambda r: _to_date(r.get("available_from")) or date.min)
    return FixedProduct(
        best["code"],
        best.get("full_name") or best.get("display_name") or best["code"],
        _to_date(best.get("available_from")),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_fixed.py::test_resolve_fixed_picks_current_oe_fix_12m tests/test_fixed.py::test_resolve_fixed_override tests/test_fixed.py::test_resolve_fixed_none_found_raises -v`
Expected: the 3 resolve tests PASS (the `fixed_resolvers` test still errors on import until Task 3 — that's fine; you can also just run the 3 named tests).

- [ ] **Step 5: Commit**

```bash
git add src/octopus_compare/tracker.py tests/test_fixed.py
git commit -m "feat: resolve the current Octopus 12M Fixed product"
```

---

### Task 3: `fixed_resolvers` (`tracker.py`)

**Files:**
- Modify: `src/octopus_compare/tracker.py`
- Test: `tests/test_fixed.py`

**Interfaces:**
- Consumes: `build_tariff_code` (account.py), `fetch_rates`/`fetch_standing_charges`/`flat_lookup` (rates.py), `FixedProduct`.
- Produces: `fixed_resolvers(client, supply: str, product: FixedProduct, region: str) -> tuple[Callable[[date], Decimal], Callable[[date], Decimal]]` — `(rate_for, sc_for)` that return the product's locked rate/standing for ANY day (flat). Fetches the locked value querying at the product's `available_from`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_fixed.py`:

```python
class FixedRateClient:
    """Serves a single flat rate / standing charge regardless of period."""

    def get_results(self, path, params=None):
        if "standing-charges" in path:
            return [{"value_exc_vat": 28.0, "valid_from": None, "valid_to": None}]
        return [{"value_exc_vat": 21.5, "valid_from": None, "valid_to": None}]


def test_fixed_resolvers_flat_across_dates():
    fp = FixedProduct("OE-FIX-12M-26-06-24", "Octopus 12M Fixed", date(2026, 6, 24))
    rate_for, sc_for = fixed_resolvers(FixedRateClient(), "electricity", fp, "C")
    # Works for dates BEFORE the product's available_from — proves it's flat, not date-gated.
    assert rate_for(date(2026, 1, 1)) == Decimal("21.5")
    assert rate_for(date(2026, 5, 31)) == Decimal("21.5")
    assert sc_for(date(2026, 1, 1)) == Decimal("28.0")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_fixed.py::test_fixed_resolvers_flat_across_dates -v`
Expected: FAIL with `ImportError: cannot import name 'fixed_resolvers'`.

- [ ] **Step 3: Write minimal implementation**

In `src/octopus_compare/tracker.py`: ensure `timedelta` is imported (change the datetime import to `from datetime import date, datetime, timedelta`) and add `flat_lookup` to the rates import (the line `from octopus_compare.rates import fetch_rates, fetch_standing_charges, VersionedLookup` becomes `from octopus_compare.rates import fetch_rates, fetch_standing_charges, VersionedLookup, flat_lookup`). Then append:

```python
def fixed_resolvers(client, supply, product, region):
    """Per-day resolvers for the 12M Fixed column: the product's locked rate is
    fetched once (at its own available_from) and applied flat to every day."""
    tariff = build_tariff_code(supply, product.product_code, region)
    anchor = product.available_from
    rates = fetch_rates(client, supply, product.product_code, tariff,
                        anchor, anchor + timedelta(days=1))
    sc = fetch_standing_charges(client, supply, product.product_code, tariff,
                                anchor, anchor + timedelta(days=1))
    rate_value = rates.rate_for(anchor)
    sc_value = sc.rate_for(anchor)
    return flat_lookup(rate_value).rate_for, flat_lookup(sc_value).rate_for
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_fixed.py tests/test_versions.py tests/test_tracker.py -v`
Expected: PASS (all fixed tests + existing tracker tests still green).

- [ ] **Step 5: Commit**

```bash
git add src/octopus_compare/tracker.py tests/test_fixed.py
git commit -m "feat: flat per-day resolvers for the 12M Fixed rate"
```

---

### Task 4: `--fixed-product` flag (`config.py`)

**Files:**
- Modify: `src/octopus_compare/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `Config` gains `fixed_product: str | None = None`; `load_config` parses `--fixed-product CODE`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_config.py`:

```python
def test_fixed_product_default_none():
    cfg = load_config([], ENV, TODAY)
    assert cfg.fixed_product is None


def test_fixed_product_flag():
    cfg = load_config(["--fixed-product", "OE-FIX-12M-26-06-24"], ENV, TODAY)
    assert cfg.fixed_product == "OE-FIX-12M-26-06-24"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_config.py::test_fixed_product_flag -v`
Expected: FAIL with `AttributeError: 'Config' object has no attribute 'fixed_product'`.

- [ ] **Step 3: Write minimal implementation**

In `src/octopus_compare/config.py`, add a field to the `Config` dataclass after `region`:

```python
    region: str | None = None
    fixed_product: str | None = None
```

Add the argparse argument after the `--region` line:

```python
    parser.add_argument("--fixed-product", dest="fixed_product", default=None)
```

And thread it into the returned `Config(...)` after `region=args.region,`:

```python
        region=args.region,
        fixed_product=args.fixed_product,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_config.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/octopus_compare/config.py tests/test_config.py
git commit -m "feat: --fixed-product flag"
```

---

### Task 5: Three-column report (`report.py`)

**Files:**
- Rewrite: `src/octopus_compare/report.py`
- Rewrite: `tests/test_report.py`

**Interfaces:**
- Consumes: `SupplyCost` (costing), `TrackerVersion` + `FixedProduct` (tracker).
- Produces:
  - `MonthlyRow(month, days, flexible_pounds, tracker_pounds, fixed_pounds)` with `.cheapest -> "flexible"|"tracker"|"fixed"`.
  - `ComparisonResult(period_from, period_to, region, tracker, fixed, elec_flexible, elec_tracker, elec_fixed, gas_flexible, gas_tracker, gas_fixed, monthly)` with properties `flexible_total`, `tracker_total`, `fixed_total`, `cheapest`.
  - `recommend(result, threshold_pct=Decimal("2")) -> "STAY"|"MARGINAL"|"SWITCH"`.
  - `format_text(result) -> str`, `format_json(result) -> str`.

- [ ] **Step 1: Write the failing test**

Replace the entire contents of `tests/test_report.py` with:

```python
import json
from datetime import date
from decimal import Decimal

from octopus_compare.costing import SupplyCost
from octopus_compare.tracker import TrackerVersion, FixedProduct
from octopus_compare.report import (
    ComparisonResult, MonthlyRow, recommend, format_text, format_json)


def _cost(total):
    t = Decimal(total)
    return SupplyCost(Decimal("800"), t, Decimal("0"), t, Decimal("0"), t)


def _result(flex, trk, fix):
    return ComparisonResult(
        period_from=date(2026, 1, 1), period_to=date(2026, 5, 31),
        region="C",
        tracker=TrackerVersion("SILVER-26-04-01", "Octopus Tracker April 2026 v1",
                               date(2026, 4, 1), None),
        fixed=FixedProduct("OE-FIX-12M-26-06-24", "Octopus 12M Fixed June 2026 v5",
                           date(2026, 6, 24)),
        elec_flexible=_cost(flex), elec_tracker=_cost(trk), elec_fixed=_cost(fix),
        gas_flexible=_cost("0"), gas_tracker=_cost("0"), gas_fixed=_cost("0"),
        monthly=[
            MonthlyRow(date(2026, 1, 1), 31, Decimal("210.40"), Decimal("194.00"), Decimal("205.10")),
            MonthlyRow(date(2026, 4, 1), 30, Decimal("158.40"), Decimal("135.10"), Decimal("152.30")),
        ],
    )


def test_totals_and_cheapest():
    r = _result("877.39", "783.83", "855.10")
    assert r.flexible_total == Decimal("877.39")
    assert r.tracker_total == Decimal("783.83")
    assert r.fixed_total == Decimal("855.10")
    assert r.cheapest == "tracker"


def test_monthly_row_cheapest_and_tiebreak():
    row = MonthlyRow(date(2026, 1, 1), 31, Decimal("194.00"), Decimal("194.00"), Decimal("205.10"))
    assert row.cheapest == "flexible"  # tie flexible vs tracker -> flexible wins
    row2 = MonthlyRow(date(2026, 1, 1), 31, Decimal("210.40"), Decimal("194.00"), Decimal("205.10"))
    assert row2.cheapest == "tracker"


def test_recommend_variants():
    assert recommend(_result("877.39", "783.83", "855.10")) == "SWITCH"   # tracker 10.7% < flex
    assert recommend(_result("783.83", "877.39", "855.10")) == "STAY"     # flexible cheapest
    assert recommend(_result("100.00", "99.00", "101.00")) == "MARGINAL"  # tracker only 1% under


def test_format_text_three_columns_and_marker():
    text = format_text(_result("877.39", "783.83", "855.10"))
    assert "Flexible" in text and "Tracker" in text and "Fixed" in text
    assert "SILVER-26-04-01" in text
    assert "OE-FIX-12M-26-06-24" in text
    assert "12M Fixed" in text
    assert "Region C" in text
    assert "✓" in text
    assert "Jan 2026" in text and "Apr 2026" in text
    assert "Cheapest over this period: TRACKER" in text


def test_format_json_structure():
    data = json.loads(format_json(_result("877.39", "783.83", "855.10")))
    assert data["region"] == "C"
    assert data["tracker"]["product_code"] == "SILVER-26-04-01"
    assert data["fixed"]["product_code"] == "OE-FIX-12M-26-06-24"
    assert data["flexible_total"] == "877.39"
    assert data["tracker_total"] == "783.83"
    assert data["fixed_total"] == "855.10"
    assert data["cheapest"] == "tracker"
    assert data["recommendation"] == "SWITCH"
    assert data["electricity"]["fixed"]["total"] == "855.10"
    assert len(data["monthly"]) == 2
    assert data["monthly"][0]["fixed"] == "205.10"
    assert data["monthly"][0]["cheapest"] == "tracker"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_report.py -v`
Expected: FAIL with `TypeError` (old `ComparisonResult` has no `fixed`/`elec_fixed`) or `ImportError`.

- [ ] **Step 3: Write minimal implementation**

Replace the entire contents of `src/octopus_compare/report.py` with:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_report.py -v`
Expected: PASS. (`tests/test_pipeline.py` will be red until Task 6 — expected.)

- [ ] **Step 5: Commit**

```bash
git add src/octopus_compare/report.py tests/test_report.py
git commit -m "feat: three-column report with cheapest marker + 3-way recommendation"
```

---

### Task 6: Wire the Fixed column into the pipeline (`pipeline.py`)

**Files:**
- Rewrite: `src/octopus_compare/pipeline.py`
- Rewrite: `tests/test_pipeline.py`
- Modify: `tests/fixtures/api_samples.py`

**Interfaces:**
- Consumes: `resolve_fixed`, `fixed_resolvers` (Task 2/3), the new `ComparisonResult`/`MonthlyRow` (Task 5), `Config.fixed_product` (Task 4), plus existing resolvers/helpers.
- Produces: `run_comparison(client, config) -> ComparisonResult` (now with the Fixed column). Keeps `PricingError`.

- [ ] **Step 1: Add fixtures**

Append to `tests/fixtures/api_samples.py`:

```python
# Listing payload for resolve_fixed (GET /products/?brand=OCTOPUS_ENERGY).
FIXED_PRODUCTS_LIST = [
    {"code": "OE-FIX-12M-26-06-24", "full_name": "Octopus 12M Fixed June 2026 v5",
     "display_name": "Octopus 12M Fixed",
     "available_from": "2026-06-24T00:00:00+01:00", "available_to": None},
    {"code": "COSY-FIX-12M-26-06-25", "full_name": "Cosy Octopus 12M Fixed",
     "display_name": "Cosy", "available_from": "2026-06-25T00:00:00+01:00", "available_to": None},
]
```

- [ ] **Step 2: Write the failing test**

Replace the entire contents of `tests/test_pipeline.py` with:

```python
from datetime import date
from decimal import Decimal

from octopus_compare.config import Config
from octopus_compare.pipeline import run_comparison
from octopus_compare.report import format_text
from tests.fixtures.api_samples import (
    ACCOUNT, ELEC_TWO_MONTH, GAS_TWO_MONTH, FIXED_PRODUCTS_LIST)


class FakeClient:
    """Tracker (SILVER, open-ended) cheapest; Fixed (OE-FIX-12M) between Tracker
    and Flexible; flat rates; two-month consumption."""

    UNIT = {"SILVER": {"electricity": 18.00, "gas": 5.00},
            "OE-FIX-12M": {"electricity": 20.00, "gas": 5.30},
            "VAR": {"electricity": 23.71, "gas": 5.63}}
    STAND = {"SILVER": {"electricity": 37.65, "gas": 28.52},
             "OE-FIX-12M": {"electricity": 38.00, "gas": 28.00},
             "VAR": {"electricity": 42.18, "gas": 28.06}}

    def get(self, path, params=None):
        if path == "accounts/A-8F18337C/":
            return ACCOUNT
        if path == "products/VAR-22-11-01/":
            return {"is_tracker": False}
        if path == "products/SILVER-24-12-31/":
            return {"code": "SILVER-24-12-31", "full_name": "Octopus Tracker Dec 2024",
                    "is_tracker": True,
                    "available_from": "2024-12-31T00:00:00Z", "available_to": None}
        raise AssertionError(path)

    def get_results(self, path, params=None):
        if path == "products/":
            return FIXED_PRODUCTS_LIST
        supply = "electricity" if "electricity" in path else "gas"
        if "consumption" in path:
            return ELEC_TWO_MONTH if supply == "electricity" else GAS_TWO_MONTH
        family = ("SILVER" if "SILVER" in path
                  else "OE-FIX-12M" if "OE-FIX-12M" in path else "VAR")
        table = self.STAND if "standing-charges" in path else self.UNIT
        return [{"value_exc_vat": table[family][supply], "valid_from": None, "valid_to": None}]


def _config():
    return Config(
        api_key="sk", account="A-8F18337C",
        period_from=date(2026, 3, 30), period_to=date(2026, 4, 2),
        output_format="text", gas_calorific_value=Decimal("39.5"),
        gas_units="kwh", verbose=False,
    )


def test_run_comparison_has_three_tariffs():
    result = run_comparison(FakeClient(), _config())
    assert result.region == "C"
    assert result.tracker.product_code == "SILVER-24-12-31"
    assert result.fixed.product_code == "OE-FIX-12M-26-06-24"
    # three independent totals; Tracker cheapest, Fixed between Tracker and Flexible
    assert result.tracker_total < result.fixed_total < result.flexible_total
    assert result.cheapest == "tracker"
    # monthly fixed totals sum to the grand fixed total
    assert sum(r.fixed_pounds for r in result.monthly) == result.fixed_total
    # per-supply fixed totals sum to the grand fixed total
    assert result.elec_fixed.total_pounds + result.gas_fixed.total_pounds == result.fixed_total
    assert [r.month for r in result.monthly] == [date(2026, 3, 1), date(2026, 4, 1)]


def test_run_comparison_text_renders_fixed():
    text = format_text(run_comparison(FakeClient(), _config()))
    assert "OE-FIX-12M-26-06-24" in text
    assert "Fixed" in text and "✓" in text
    assert "Mar 2026" in text and "Apr 2026" in text
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_pipeline.py -v`
Expected: FAIL (current `run_comparison` builds the old 2-tariff `ComparisonResult`; `result.fixed` / `fixed_total` don't exist).

- [ ] **Step 4: Write minimal implementation**

Replace the entire contents of `src/octopus_compare/pipeline.py` with:

```python
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
    return region, latest, months["flexible"], months["tracker"], months["fixed"]


def _month_total(em, gm, month):
    e = em.get(month, (set(), None))[1]
    g = gm.get(month, (set(), None))[1]
    return (e.total_pounds if e else 0) + (g.total_pounds if g else 0)


def run_comparison(client, config: Config) -> ComparisonResult:
    info = parse_account(client.get(f"accounts/{config.account}/"))
    fixed_product = resolve_fixed(client, config.fixed_product)

    e_region, e_latest, e_flex, e_trk, e_fix = _supply_breakdown(
        client, "electricity", info.electricity, config, fixed_product)
    _g_region, _g_latest, g_flex, g_trk, g_fix = _supply_breakdown(
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
            tracker_pounds=_month_total(e_trk, g_trk, month),
            fixed_pounds=_month_total(e_fix, g_fix, month)))

    return ComparisonResult(
        period_from=config.period_from, period_to=config.period_to,
        region=e_region, tracker=e_latest, fixed=fixed_product,
        elec_flexible=agg(e_flex), elec_tracker=agg(e_trk), elec_fixed=agg(e_fix),
        gas_flexible=agg(g_flex), gas_tracker=agg(g_trk), gas_fixed=agg(g_fix),
        monthly=monthly,
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_pipeline.py -v`
Expected: PASS.

- [ ] **Step 6: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS (all offline tests; `test_live_eval.py` skipped without `OCTOPUS_LIVE_EVAL`).

- [ ] **Step 7: Commit**

```bash
git add src/octopus_compare/pipeline.py tests/test_pipeline.py tests/fixtures/api_samples.py
git commit -m "feat: price and assemble the 12M Fixed column in the pipeline"
```

---

### Task 7: README update

**Files:**
- Modify: `README.md`

**Interfaces:** none (docs only).

- [ ] **Step 1: Update the description and usage**

In `README.md`, update the project description to mention three tariffs, e.g.:

```
Compare what Octopus **Flexible**, **Tracker**, and a **12M Fixed** lock-in would
cost on your real usage, month by month, and get a recommendation. All three columns
are pure what-ifs (your consumption × each tariff's published rates) — none is your
actual bill. Tracker uses the version current each month; 12M Fixed uses today's
locked rate applied flat; the report marks the cheapest of the three each month.
```

Add a usage example for the new flag in the Usage section:

```
    octopus-compare --fixed-product OE-FIX-12M-26-06-24   # pin a specific 12M Fixed version
```

- [ ] **Step 2: Verify the flag is exposed**

Run: `.venv/bin/python -m octopus_compare.cli --help`
Expected: `--fixed-product` appears alongside `--tracker-product` and `--region`.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: README for the 12M Fixed comparison column"
```

---

## Self-Review

**Spec coverage** (each §2–§11 requirement → task):
- Product `OE-FIX-12M-*`, listed, current/override → Task 2 (`resolve_fixed`).
- Today's locked rate, flat → Task 1 (`flat_lookup`) + Task 3 (`fixed_resolvers`).
- Three columns + cheapest `✓` marker → Task 5 (`_cheapest`, `_cell`, `_block`, monthly loop).
- 3-way recommendation framed vs Flexible + runner-up → Task 5 (`recommend`, `_recommendation_lines`).
- Always-on Fixed column + `--fixed-product` override → Tasks 4, 6.
- Flat rate sidesteps coverage gap; engine untouched; slice-&-reuse → Task 6 (`_price_months`, `fixed_resolvers`); `costing.py` not touched.
- Graceful errors (no fixed product → ValueError caught by cli; fixed rate unreadable → PricingError) → Task 2 (ValueError) + Task 6 (PricingError wrap). `cli.main` already catches `(ApiError, PricingError, ValueError)` (unchanged from the prior feature).
- JSON mirrors structure (fixed meta, monthly fixed + cheapest, fixed_total, cheapest) → Task 5 (`format_json`).
- Region per supply unchanged; fixed tariff code reuses region → Task 6.

**Placeholder scan:** none — every code step is complete; no "handle errors" hand-waves (errors are concrete `ValueError`/`KeyError`→`PricingError`).

**Type consistency:** `FixedProduct(product_code, display_name, available_from)` defined in Task 2, imported in Task 5 (`report.py`) and constructed by `resolve_fixed` (used in Task 6). `fixed_resolvers(client, supply, product, region)` defined Task 3, called Task 6. `MonthlyRow(month, days, flexible_pounds, tracker_pounds, fixed_pounds)` defined Task 5, constructed Task 6. `ComparisonResult` field list matches between Task 5 (definition) and Task 6 (construction): `period_from, period_to, region, tracker, fixed, elec_flexible, elec_tracker, elec_fixed, gas_flexible, gas_tracker, gas_fixed, monthly`. `flat_lookup(value)` defined Task 1, used Task 3. `resolve_fixed(client, override=None)` defined Task 2, called Task 6 with `config.fixed_product`. `Config.fixed_product` added Task 4, read Task 6.

**Note on dropped fields:** the rewritten `report.py` removes the old `ComparisonResult.delta`/`pct` properties and the JSON `delta`/`pct` keys (replaced by per-tariff totals + `cheapest`). Nothing else references them (`pipeline.py`/`cli.py` use only `format_text`/`format_json`), so this is safe.
