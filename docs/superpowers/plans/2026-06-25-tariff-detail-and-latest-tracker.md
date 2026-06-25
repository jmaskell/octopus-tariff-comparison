# Fine-Grained Tariff Comparison + Latest Tracker — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `octopus-compare` into a month-by-month **Flexible-vs-Tracker** backtest with a per-supply component breakdown, comparing against the **latest published** Octopus Tracker version.

**Architecture:** Both columns are pure hypotheticals costed on the same real consumption: **Flexible** = the household's Flexible product rates by date; **Tracker** = whichever Tracker version was the current sign-up product each day (discovered by chain-walking `/products/{code}/`, since `SILVER` is unlisted). The penny-exact cost engine is reused unchanged — `pipeline.py` slices consumption into calendar months and calls `supply_cost()` per month, per supply, per tariff, then aggregates. Region is read from the account's own tariff codes and reused to build region-correct Tracker/Flexible codes.

**Tech Stack:** Python 3, `requests`, `python-dotenv`, `pytest`, `Decimal` money. No new dependencies.

## Global Constraints

- **Do NOT modify the cost engine** in `costing.py` (`daily_energy_pence`, `standing_pence`, `supply_cost`, `SupplyCost`). Only *add* `sum_supply_costs` and `month_slices`. The existing bill evals in `tests/test_costing.py` must keep passing to the penny.
- **Money:** `Decimal` everywhere; reuse `octopus_compare.money` (`round_pence`, `vat_pence`, `pounds`). Rates are matched/summed in **exc-VAT** pence; VAT (5%) is applied per month via `supply_cost`.
- **Rate values:** `build_lookup` keys on `value_exc_vat` (already). Keep using it.
- **Tariff code format:** `{E|G}-1R-{product}-{region}` (e.g. `E-1R-SILVER-26-04-01-B`). Region is the **trailing letter** of any of the account's tariff codes.
- **Tracker codename:** derive from the product code (`"-".join(code.split("-")[:-3])`) — do NOT hard-code `SILVER`.
- **API client:** use `client.get(path)` / `client.get_results(path, params)`; auth/pagination/retry already handled. `ApiError` is raised on non-retryable HTTP errors.
- **Tests:** `pytest`; inline `FakeClient` classes routing by `path`; shared fixtures in `tests/fixtures/api_samples.py`. Run from repo root.
- **Commit after every task.** Conventional-commit style messages.

## File Structure

- `src/octopus_compare/account.py` (modify) — add `region_letter`, `build_tariff_code`.
- `src/octopus_compare/costing.py` (modify, additive) — add `sum_supply_costs`, `month_slices`.
- `src/octopus_compare/rates.py` (modify) — add `VersionedLookup`.
- `src/octopus_compare/tracker.py` (modify) — `TrackerVersion`, chain-walk discovery, window version gathering, `resolve_flexible`, `tracker_resolvers`. (Keep existing `TrackerTariff`/`resolve_tracker` so `tests/test_tracker.py` stays green.)
- `src/octopus_compare/config.py` (modify) — add `--tracker-product`, `--region`.
- `src/octopus_compare/report.py` (rewrite) — new `ComparisonResult`, `MonthlyRow`, formatters.
- `src/octopus_compare/pipeline.py` (rewrite) — assemble the new result.
- `src/octopus_compare/cli.py` (unchanged) — already delegates to `run_comparison` + `format_*`.
- Tests: new `tests/test_versions.py` (chain-walk + window gather + flexible), additions to `test_account.py`, `test_costing.py`, `test_rates.py`, `test_config.py`; rewrites of `test_report.py`, `test_pipeline.py`; fixtures in `tests/fixtures/api_samples.py`.

---

### Task 1: Region helper + tariff-code builder (`account.py`)

**Files:**
- Modify: `src/octopus_compare/account.py`
- Test: `tests/test_account.py`

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `region_letter(tariff_code: str) -> str` — trailing region letter.
  - `build_tariff_code(supply: str, product_code: str, region: str) -> str` — `{E|G}-1R-{product}-{region}`; `supply` is `"electricity"` or `"gas"`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_account.py`:

```python
from octopus_compare.account import region_letter, build_tariff_code


def test_region_letter():
    assert region_letter("E-1R-SILVER-24-12-31-C") == "C"
    assert region_letter("G-1R-VAR-22-11-01-B") == "B"


def test_build_tariff_code():
    assert build_tariff_code("electricity", "SILVER-26-04-01", "C") == "E-1R-SILVER-26-04-01-C"
    assert build_tariff_code("gas", "SILVER-26-04-01", "C") == "G-1R-SILVER-26-04-01-C"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_account.py::test_region_letter tests/test_account.py::test_build_tariff_code -v`
Expected: FAIL with `ImportError: cannot import name 'region_letter'`.

- [ ] **Step 3: Write minimal implementation**

Append to `src/octopus_compare/account.py`:

```python
def region_letter(tariff_code: str) -> str:
    return tariff_code[-1]


def build_tariff_code(supply: str, product_code: str, region: str) -> str:
    prefix = "E" if supply == "electricity" else "G"
    return f"{prefix}-1R-{product_code}-{region}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_account.py -v`
Expected: PASS (all account tests).

- [ ] **Step 5: Commit**

```bash
git add src/octopus_compare/account.py tests/test_account.py
git commit -m "feat: region letter + tariff-code builder"
```

---

### Task 2: `sum_supply_costs` aggregation (`costing.py`)

**Files:**
- Modify: `src/octopus_compare/costing.py`
- Test: `tests/test_costing.py`

**Interfaces:**
- Consumes: `SupplyCost` (existing).
- Produces: `sum_supply_costs(costs: list[SupplyCost]) -> SupplyCost` — component-wise sum; empty list → all-zero `SupplyCost`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_costing.py`:

```python
from octopus_compare.costing import sum_supply_costs, SupplyCost
from decimal import Decimal as D


def test_sum_supply_costs_adds_components():
    a = SupplyCost(D("10"), D("1.00"), D("0.50"), D("1.50"), D("0.08"), D("1.58"))
    b = SupplyCost(D("20"), D("2.00"), D("0.50"), D("2.50"), D("0.13"), D("2.63"))
    total = sum_supply_costs([a, b])
    assert total.consumption_kwh == D("30")
    assert total.energy_pounds == D("3.00")
    assert total.standing_pounds == D("1.00")
    assert total.subtotal_pounds == D("4.00")
    assert total.vat_pounds == D("0.21")
    assert total.total_pounds == D("4.21")


def test_sum_supply_costs_empty_is_zero():
    total = sum_supply_costs([])
    assert total.total_pounds == D("0")
    assert total.consumption_kwh == D("0")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_costing.py::test_sum_supply_costs_adds_components -v`
Expected: FAIL with `ImportError: cannot import name 'sum_supply_costs'`.

- [ ] **Step 3: Write minimal implementation**

Append to `src/octopus_compare/costing.py`:

```python
def sum_supply_costs(costs: list[SupplyCost]) -> SupplyCost:
    z = Decimal(0)

    def s(attr: str) -> Decimal:
        return sum((getattr(c, attr) for c in costs), z)

    return SupplyCost(
        consumption_kwh=s("consumption_kwh"),
        energy_pounds=s("energy_pounds"),
        standing_pounds=s("standing_pounds"),
        subtotal_pounds=s("subtotal_pounds"),
        vat_pounds=s("vat_pounds"),
        total_pounds=s("total_pounds"),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_costing.py -v`
Expected: PASS (including the existing penny-exact bill evals — confirm they still pass).

- [ ] **Step 5: Commit**

```bash
git add src/octopus_compare/costing.py tests/test_costing.py
git commit -m "feat: sum_supply_costs component-wise aggregation"
```

---

### Task 3: `month_slices` calendar bucketing (`costing.py`)

**Files:**
- Modify: `src/octopus_compare/costing.py`
- Test: `tests/test_costing.py`

**Interfaces:**
- Produces: `month_slices(daily_kwh: dict[date, Decimal]) -> list[tuple[date, dict[date, Decimal]]]` — `(first-of-month, {day: kwh})` pairs, ascending by month, each sub-dict holding only that month's days.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_costing.py`:

```python
from octopus_compare.costing import month_slices


def test_month_slices_groups_by_calendar_month():
    daily = {
        date(2026, 3, 30): D("9"),
        date(2026, 3, 31): D("8"),
        date(2026, 4, 1): D("7"),
    }
    slices = month_slices(daily)
    assert [m for m, _ in slices] == [date(2026, 3, 1), date(2026, 4, 1)]
    assert slices[0][1] == {date(2026, 3, 30): D("9"), date(2026, 3, 31): D("8")}
    assert slices[1][1] == {date(2026, 4, 1): D("7")}


def test_month_slices_empty():
    assert month_slices({}) == []
```

(`date` and `D` are already imported at the top of `tests/test_costing.py` from earlier tasks; if not, add `from datetime import date`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_costing.py::test_month_slices_groups_by_calendar_month -v`
Expected: FAIL with `ImportError: cannot import name 'month_slices'`.

- [ ] **Step 3: Write minimal implementation**

Append to `src/octopus_compare/costing.py`:

```python
def month_slices(
    daily_kwh: dict[date, Decimal],
) -> list[tuple[date, dict[date, Decimal]]]:
    buckets: dict[date, dict[date, Decimal]] = {}
    for day, kwh in daily_kwh.items():
        buckets.setdefault(day.replace(day=1), {})[day] = kwh
    return [(month, buckets[month]) for month in sorted(buckets)]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_costing.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/octopus_compare/costing.py tests/test_costing.py
git commit -m "feat: month_slices calendar bucketing"
```

---

### Task 4: `VersionedLookup` — pick a rate lookup by date (`rates.py`)

**Files:**
- Modify: `src/octopus_compare/rates.py`
- Test: `tests/test_rates.py`

**Interfaces:**
- Consumes: existing `RateLookup` (has `.rate_for(day) -> Decimal`).
- Produces: `VersionedLookup(entries: list[tuple[date, date | None, RateLookup]])` with `.rate_for(day: date) -> Decimal`. Each entry is `(available_from, available_to, lookup)`; for a day, the entry whose `[available_from, available_to)` covers it delegates to its lookup. `available_to=None` means open-ended. Raises `KeyError` if no entry covers the day.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_rates.py`:

```python
from octopus_compare.rates import VersionedLookup, RateLookup, _Window


def _flat_lookup(value):
    return RateLookup([_Window(date.min, date.max, Decimal(value))])


def test_versioned_lookup_picks_by_date():
    sep = (date(2025, 9, 2), date(2026, 4, 1), _flat_lookup("18.00"))
    apr = (date(2026, 4, 1), None, _flat_lookup("20.00"))
    vl = VersionedLookup([apr, sep])  # unordered on purpose
    assert vl.rate_for(date(2026, 3, 15)) == Decimal("18.00")
    assert vl.rate_for(date(2026, 4, 15)) == Decimal("20.00")


def test_versioned_lookup_uncovered_raises():
    vl = VersionedLookup([(date(2026, 4, 1), None, _flat_lookup("20.00"))])
    with pytest.raises(KeyError):
        vl.rate_for(date(2026, 3, 1))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_rates.py::test_versioned_lookup_picks_by_date -v`
Expected: FAIL with `ImportError: cannot import name 'VersionedLookup'`.

- [ ] **Step 3: Write minimal implementation**

Append to `src/octopus_compare/rates.py` (`date` is already imported there):

```python
class VersionedLookup:
    """Pick, per day, the RateLookup of the version whose availability window
    covers that day, then delegate. Used for the multi-version Tracker series."""

    def __init__(self, entries: list[tuple[date, date | None, RateLookup]]):
        self._entries = sorted(entries, key=lambda e: e[0])

    def rate_for(self, day: date) -> Decimal:
        for start, end, lookup in self._entries:
            if start <= day < (end or date.max):
                return lookup.rate_for(day)
        raise KeyError(f"No Tracker version covering {day}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_rates.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/octopus_compare/rates.py tests/test_rates.py
git commit -m "feat: VersionedLookup selects rate lookup by date"
```

---

### Task 5: Tracker version chain-walk discovery (`tracker.py`)

**Files:**
- Modify: `src/octopus_compare/tracker.py`
- Test: `tests/test_versions.py` (create)
- Modify: `tests/fixtures/api_samples.py`

**Interfaces:**
- Consumes: `client.get(path)`, `ApiError`.
- Produces:
  - `TrackerVersion(product_code: str, display_name: str, available_from: date, available_to: date | None)` (dataclass).
  - `discover_chain(client, seed_product: str) -> list[TrackerVersion]` — from `seed_product`, follow `available_to → next code` until open-ended (`available_to is None`) or a constructed code 404s; returns versions oldest-seed-first.
  - Internal helpers `_next_code(product_code: str, available_to: date) -> str` and `_version_from_detail(code: str, detail: dict) -> TrackerVersion`.

- [ ] **Step 1: Add fixtures**

Append to `tests/fixtures/api_samples.py`:

```python
# Tracker product details, forming a chain via available_to -> next available_from.
TRACKER_PRODUCTS = {
    "SILVER-25-04-15": {
        "code": "SILVER-25-04-15", "full_name": "Octopus Tracker April 2025 v2",
        "is_tracker": True,
        "available_from": "2025-04-15T00:00:00+01:00",
        "available_to": "2025-09-02T00:00:00+01:00",
    },
    "SILVER-25-09-02": {
        "code": "SILVER-25-09-02", "full_name": "Octopus Tracker September 2025 v1",
        "is_tracker": True,
        "available_from": "2025-09-02T00:00:00+01:00",
        "available_to": "2026-04-01T00:00:00+01:00",
    },
    "SILVER-26-04-01": {
        "code": "SILVER-26-04-01", "full_name": "Octopus Tracker April 2026 v1",
        "is_tracker": True,
        "available_from": "2026-04-01T00:00:00+01:00",
        "available_to": None,
    },
}
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_versions.py`:

```python
from datetime import date

import pytest

from octopus_compare.client import ApiError
from octopus_compare.tracker import discover_chain, _next_code, TrackerVersion
from tests.fixtures.api_samples import TRACKER_PRODUCTS


class ProductClient:
    """Serves product details from TRACKER_PRODUCTS; 404s anything else."""

    def __init__(self, products=TRACKER_PRODUCTS, missing=()):
        self._products = products
        self._missing = set(missing)

    def get(self, path, params=None):
        code = path.split("/")[1]
        if code in self._missing or code not in self._products:
            raise ApiError(f"GET {path} failed: HTTP 404")
        return self._products[code]


def test_next_code_from_available_to():
    assert _next_code("SILVER-25-04-15", date(2025, 9, 2)) == "SILVER-25-09-02"
    assert _next_code("SILVER-25-09-02", date(2026, 4, 1)) == "SILVER-26-04-01"


def test_discover_chain_walks_to_latest():
    chain = discover_chain(ProductClient(), "SILVER-25-04-15")
    assert [v.product_code for v in chain] == [
        "SILVER-25-04-15", "SILVER-25-09-02", "SILVER-26-04-01"]
    latest = chain[-1]
    assert latest.available_to is None
    assert latest.display_name == "Octopus Tracker April 2026 v1"
    assert latest.available_from == date(2026, 4, 1)


def test_discover_chain_seed_is_latest():
    chain = discover_chain(ProductClient(), "SILVER-26-04-01")
    assert [v.product_code for v in chain] == ["SILVER-26-04-01"]


def test_discover_chain_stops_on_404():
    chain = discover_chain(ProductClient(missing=["SILVER-26-04-01"]), "SILVER-25-09-02")
    assert [v.product_code for v in chain] == ["SILVER-25-09-02"]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_versions.py -v`
Expected: FAIL with `ImportError: cannot import name 'discover_chain'`.

- [ ] **Step 4: Write minimal implementation**

Add to `src/octopus_compare/tracker.py` (keep the existing `TrackerTariff`/`resolve_tracker`; add new imports at top):

```python
from datetime import datetime
from zoneinfo import ZoneInfo

from octopus_compare.client import ApiError

_LONDON = ZoneInfo("Europe/London")


@dataclass
class TrackerVersion:
    product_code: str
    display_name: str
    available_from: date
    available_to: date | None


def _to_date(value: str | None) -> date | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(_LONDON).date()


def _version_from_detail(code: str, detail: dict) -> TrackerVersion:
    return TrackerVersion(
        product_code=code,
        display_name=detail.get("full_name") or detail.get("display_name") or code,
        available_from=_to_date(detail.get("available_from")),
        available_to=_to_date(detail.get("available_to")),
    )


def _next_code(product_code: str, available_to: date) -> str:
    codename = "-".join(product_code.split("-")[:-3])
    return f"{codename}-{available_to:%y-%m-%d}"


def discover_chain(client, seed_product: str) -> list[TrackerVersion]:
    versions: list[TrackerVersion] = []
    code: str | None = seed_product
    seen: set[str] = set()
    while code and code not in seen:
        seen.add(code)
        try:
            detail = client.get(f"products/{code}/")
        except ApiError:
            break
        version = _version_from_detail(code, detail)
        versions.append(version)
        if version.available_to is None:
            break
        code = _next_code(code, version.available_to)
    return versions
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_versions.py tests/test_tracker.py -v`
Expected: PASS (new discovery tests + the existing `resolve_tracker` tests still green).

- [ ] **Step 6: Commit**

```bash
git add src/octopus_compare/tracker.py tests/test_versions.py tests/fixtures/api_samples.py
git commit -m "feat: chain-walk discovery of Tracker versions"
```

---

### Task 6: Gather window versions + identify latest (`tracker.py`)

**Files:**
- Modify: `src/octopus_compare/tracker.py`
- Test: `tests/test_versions.py`

**Interfaces:**
- Consumes: `MeterPoint`/`Agreement` (existing), `product_code_from_tariff` (existing), `discover_chain`, `_version_from_detail` (Task 5).
- Produces:
  - `tracker_versions_for_window(client, meter_point, period_from: date, period_to: date) -> list[TrackerVersion]` — Tracker versions whose availability window intersects `[period_from, period_to)`, sorted ascending by `available_from`. Anchored on the account's Tracker agreement history plus the forward chain-walk to the latest. Raises `ValueError` if the account has no Tracker in history.
  - `latest_tracker_version(versions: list[TrackerVersion]) -> TrackerVersion` — the open-ended (`available_to is None`) version, else the newest by `available_from`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_versions.py`:

```python
from octopus_compare.account import MeterPoint, Agreement
from octopus_compare.tracker import (
    tracker_versions_for_window, latest_tracker_version)


def _tracker_meter(tracker_codes):
    agreements = [
        Agreement(f"E-1R-{c}-C", date(2025, 1, 1), date(2026, 4, 1)) for c in tracker_codes
    ] + [Agreement("E-1R-VAR-22-11-01-C", date(2026, 4, 1), None)]
    return MeterPoint("mpan", ["s"], agreements)


class WindowClient(ProductClient):
    def get(self, path, params=None):
        code = path.split("/")[1]
        if code == "VAR-22-11-01":
            return {"is_tracker": False}
        return super().get(path, params)


def test_window_versions_history_anchor_plus_chain():
    # On the Sep-2025 version; window spans into the Apr-2026 era.
    meter = _tracker_meter(["SILVER-25-09-02"])
    versions = tracker_versions_for_window(
        WindowClient(), meter, date(2026, 1, 1), date(2026, 5, 1))
    assert [v.product_code for v in versions] == ["SILVER-25-09-02", "SILVER-26-04-01"]
    assert latest_tracker_version(versions).product_code == "SILVER-26-04-01"


def test_window_versions_includes_older_anchor():
    # History has an older version too; window starts in its era.
    meter = _tracker_meter(["SILVER-25-04-15", "SILVER-25-09-02"])
    versions = tracker_versions_for_window(
        WindowClient(), meter, date(2025, 5, 1), date(2025, 10, 1))
    assert [v.product_code for v in versions] == ["SILVER-25-04-15", "SILVER-25-09-02"]


def test_window_versions_no_tracker_raises():
    meter = MeterPoint("mpan", ["s"], [Agreement("E-1R-VAR-22-11-01-C", date(2026, 4, 1), None)])
    with pytest.raises(ValueError):
        tracker_versions_for_window(WindowClient(), meter, date(2026, 1, 1), date(2026, 5, 1))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_versions.py::test_window_versions_history_anchor_plus_chain -v`
Expected: FAIL with `ImportError: cannot import name 'tracker_versions_for_window'`.

- [ ] **Step 3: Write minimal implementation**

Append to `src/octopus_compare/tracker.py`:

```python
def _tracker_anchors(client, meter_point) -> list[str]:
    """Distinct Tracker product codes in the meter's agreement history, newest-first."""
    anchors: list[str] = []
    seen: set[str] = set()
    for agreement in sorted(
        meter_point.agreements, key=lambda a: a.valid_from or date.min, reverse=True
    ):
        product = product_code_from_tariff(agreement.tariff_code)
        if product in seen:
            continue
        seen.add(product)
        if client.get(f"products/{product}/").get("is_tracker"):
            anchors.append(product)
    return anchors


def tracker_versions_for_window(
    client, meter_point, period_from: date, period_to: date
) -> list[TrackerVersion]:
    anchors = _tracker_anchors(client, meter_point)
    if not anchors:
        raise ValueError("No Tracker tariff found in this account's agreement history")
    by_code = {v.product_code: v for v in discover_chain(client, anchors[0])}
    for code in anchors[1:]:
        if code not in by_code:
            by_code[code] = _version_from_detail(code, client.get(f"products/{code}/"))
    versions = sorted(by_code.values(), key=lambda v: v.available_from)
    return [
        v for v in versions
        if v.available_from < period_to and (v.available_to or date.max) > period_from
    ]


def latest_tracker_version(versions: list[TrackerVersion]) -> TrackerVersion:
    for version in versions:
        if version.available_to is None:
            return version
    return max(versions, key=lambda v: v.available_from)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_versions.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/octopus_compare/tracker.py tests/test_versions.py
git commit -m "feat: gather window-intersecting Tracker versions + latest"
```

---

### Task 7: Resolve the household's Flexible tariff (`tracker.py`)

**Files:**
- Modify: `src/octopus_compare/tracker.py`
- Test: `tests/test_versions.py`

**Interfaces:**
- Produces:
  - `FlexibleTariff(product_code: str, tariff_code: str)` (dataclass).
  - `resolve_flexible(client, meter_point) -> FlexibleTariff` — newest agreement whose product is **not** a tracker (via `products/{code}/` `is_tracker`). Raises `ValueError` if none.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_versions.py`:

```python
from octopus_compare.tracker import resolve_flexible, FlexibleTariff


def test_resolve_flexible_picks_newest_non_tracker():
    meter = MeterPoint("mpan", ["s"], [
        Agreement("E-1R-SILVER-25-09-02-C", date(2025, 1, 1), date(2026, 4, 1)),
        Agreement("E-1R-VAR-22-11-01-C", date(2026, 4, 1), None),
    ])
    flex = resolve_flexible(WindowClient(), meter)
    assert flex == FlexibleTariff(product_code="VAR-22-11-01", tariff_code="E-1R-VAR-22-11-01-C")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_versions.py::test_resolve_flexible_picks_newest_non_tracker -v`
Expected: FAIL with `ImportError: cannot import name 'resolve_flexible'`.

- [ ] **Step 3: Write minimal implementation**

Append to `src/octopus_compare/tracker.py`:

```python
@dataclass
class FlexibleTariff:
    product_code: str
    tariff_code: str


def resolve_flexible(client, meter_point) -> FlexibleTariff:
    for agreement in sorted(
        meter_point.agreements, key=lambda a: a.valid_from or date.min, reverse=True
    ):
        product = product_code_from_tariff(agreement.tariff_code)
        if not client.get(f"products/{product}/").get("is_tracker"):
            return FlexibleTariff(product_code=product, tariff_code=agreement.tariff_code)
    raise ValueError("No Flexible tariff found in this account's agreement history")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_versions.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/octopus_compare/tracker.py tests/test_versions.py
git commit -m "feat: resolve household Flexible tariff"
```

---

### Task 8: Per-day Tracker rate/standing resolvers (`tracker.py`)

**Files:**
- Modify: `src/octopus_compare/tracker.py`
- Test: `tests/test_versions.py`

**Interfaces:**
- Consumes: `VersionedLookup` (Task 4), `build_tariff_code` (Task 1), `fetch_rates`/`fetch_standing_charges` (existing in `rates.py`).
- Produces: `tracker_resolvers(client, supply: str, versions: list[TrackerVersion], region: str, period_from: date, period_to: date) -> tuple[Callable[[date], Decimal], Callable[[date], Decimal]]` — `(rate_for, sc_for)`, each picking the right version's lookup per day. Region-correct tariff codes are built per version.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_versions.py`:

```python
from decimal import Decimal
from octopus_compare.tracker import tracker_resolvers


class TrackerRateClient:
    """Different unit rate / standing charge per Tracker product code in the path."""

    UNIT = {"SILVER-25-09-02": "18.00", "SILVER-26-04-01": "20.00"}
    STAND = {"SILVER-25-09-02": "37.00", "SILVER-26-04-01": "38.00"}

    def get_results(self, path, params=None):
        product = path.split("/")[1]
        if "standing-charges" in path:
            return [{"value_exc_vat": float(self.STAND[product]),
                     "valid_from": None, "valid_to": None}]
        return [{"value_exc_vat": float(self.UNIT[product]),
                 "valid_from": None, "valid_to": None}]


def test_tracker_resolvers_pick_version_per_day():
    versions = [
        TrackerVersion("SILVER-25-09-02", "Sep 2025", date(2025, 9, 2), date(2026, 4, 1)),
        TrackerVersion("SILVER-26-04-01", "Apr 2026", date(2026, 4, 1), None),
    ]
    rate_for, sc_for = tracker_resolvers(
        TrackerRateClient(), "electricity", versions, "C", date(2026, 3, 1), date(2026, 5, 1))
    assert rate_for(date(2026, 3, 15)) == Decimal("18.00")
    assert rate_for(date(2026, 4, 15)) == Decimal("20.00")
    assert sc_for(date(2026, 3, 15)) == Decimal("37.00")
    assert sc_for(date(2026, 4, 15)) == Decimal("38.00")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_versions.py::test_tracker_resolvers_pick_version_per_day -v`
Expected: FAIL with `ImportError: cannot import name 'tracker_resolvers'`.

- [ ] **Step 3: Write minimal implementation**

Add the import near the top of `src/octopus_compare/tracker.py`:

```python
from octopus_compare.account import MeterPoint, product_code_from_tariff, build_tariff_code
from octopus_compare.rates import fetch_rates, fetch_standing_charges, VersionedLookup
```

(Replace the existing `from octopus_compare.account import ...` line so it also imports `build_tariff_code`.)

Append:

```python
def tracker_resolvers(client, supply, versions, region, period_from, period_to):
    rate_entries = []
    sc_entries = []
    for version in versions:
        tariff = build_tariff_code(supply, version.product_code, region)
        rate_entries.append((
            version.available_from, version.available_to,
            fetch_rates(client, supply, version.product_code, tariff, period_from, period_to),
        ))
        sc_entries.append((
            version.available_from, version.available_to,
            fetch_standing_charges(client, supply, version.product_code, tariff, period_from, period_to),
        ))
    return VersionedLookup(rate_entries).rate_for, VersionedLookup(sc_entries).rate_for
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_versions.py tests/test_tracker.py tests/test_rates.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/octopus_compare/tracker.py tests/test_versions.py
git commit -m "feat: per-day Tracker rate/standing resolvers across versions"
```

---

### Task 9: `--tracker-product` / `--region` config flags (`config.py`)

**Files:**
- Modify: `src/octopus_compare/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `Config` gains `tracker_product: str | None = None` and `region: str | None = None`; `load_config` parses `--tracker-product CODE` and `--region X`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_config.py`:

```python
def test_tracker_product_and_region_default_none():
    cfg = load_config([], ENV, TODAY)
    assert cfg.tracker_product is None
    assert cfg.region is None


def test_tracker_product_and_region_flags():
    cfg = load_config(
        ["--tracker-product", "SILVER-26-04-01", "--region", "C"], ENV, TODAY)
    assert cfg.tracker_product == "SILVER-26-04-01"
    assert cfg.region == "C"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py::test_tracker_product_and_region_flags -v`
Expected: FAIL with `AttributeError: 'Config' object has no attribute 'tracker_product'`.

- [ ] **Step 3: Write minimal implementation**

In `src/octopus_compare/config.py`, add two fields to the `Config` dataclass (after `verbose`):

```python
    verbose: bool
    tracker_product: str | None = None
    region: str | None = None
```

Add two arguments in `load_config` (after the `--verbose` line):

```python
    parser.add_argument("--tracker-product", dest="tracker_product", default=None)
    parser.add_argument("--region", dest="region", default=None)
```

And pass them into the returned `Config(...)` (after `verbose=args.verbose,`):

```python
        verbose=args.verbose,
        tracker_product=args.tracker_product,
        region=args.region,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_config.py -v`
Expected: PASS (existing default tests still pass).

- [ ] **Step 5: Commit**

```bash
git add src/octopus_compare/config.py tests/test_config.py
git commit -m "feat: --tracker-product and --region flags"
```

---

### Task 10: New report model + formatters (`report.py`)

**Files:**
- Rewrite: `src/octopus_compare/report.py`
- Rewrite: `tests/test_report.py`

**Interfaces:**
- Consumes: `SupplyCost` (costing), `TrackerVersion` (tracker).
- Produces:
  - `MonthlyRow(month: date, days: int, flexible_pounds: Decimal, tracker_pounds: Decimal)` with `.delta` property (`tracker − flexible`).
  - `ComparisonResult(period_from, period_to, region: str, tracker: TrackerVersion, elec_flexible: SupplyCost, elec_tracker: SupplyCost, gas_flexible: SupplyCost, gas_tracker: SupplyCost, monthly: list[MonthlyRow])` with properties `flexible_total`, `tracker_total`, `delta`, `pct`.
  - `recommend(result, threshold_pct=Decimal("2")) -> str` (`"SWITCH BACK"` / `"STAY"` / `"MARGINAL"`).
  - `format_text(result) -> str`, `format_json(result) -> str`.

- [ ] **Step 1: Write the failing test**

Replace the entire contents of `tests/test_report.py` with:

```python
import json
from datetime import date
from decimal import Decimal

from octopus_compare.costing import SupplyCost
from octopus_compare.tracker import TrackerVersion
from octopus_compare.report import (
    ComparisonResult, MonthlyRow, recommend, format_text, format_json)


def _cost(consumption, energy, standing, vat, total):
    d = Decimal
    return SupplyCost(d(consumption), d(energy), d(standing),
                      d(energy) + d(standing), d(vat), d(total))


def _result(flex_total, trk_total):
    f = _cost("800", flex_total, "0", "0", flex_total)
    t = _cost("800", trk_total, "0", "0", trk_total)
    zero = _cost("0", "0", "0", "0", "0")
    return ComparisonResult(
        period_from=date(2026, 1, 1), period_to=date(2026, 5, 31),
        region="C",
        tracker=TrackerVersion("SILVER-26-04-01", "Octopus Tracker April 2026 v1",
                               date(2026, 4, 1), None),
        elec_flexible=f, elec_tracker=t, gas_flexible=zero, gas_tracker=zero,
        monthly=[
            MonthlyRow(date(2026, 1, 1), 31, Decimal("210.40"), Decimal("194.00")),
            MonthlyRow(date(2026, 4, 1), 30, Decimal("158.40"), Decimal("135.10")),
        ],
    )


def test_totals_delta_and_pct():
    r = _result("877.39", "783.83")
    assert r.flexible_total == Decimal("877.39")
    assert r.tracker_total == Decimal("783.83")
    assert r.delta == Decimal("-93.56")
    assert r.pct == Decimal("-10.7")


def test_monthly_row_delta():
    row = MonthlyRow(date(2026, 1, 1), 31, Decimal("210.40"), Decimal("194.00"))
    assert row.delta == Decimal("-16.40")


def test_recommend_variants():
    assert recommend(_result("877.39", "783.83")) == "SWITCH BACK"
    assert recommend(_result("783.83", "877.39")) == "STAY"
    assert recommend(_result("100.00", "101.00")) == "MARGINAL"


def test_format_text_has_columns_blocks_and_tracker():
    text = format_text(_result("877.39", "783.83"))
    assert "Flexible" in text and "Tracker" in text
    assert "SILVER-26-04-01" in text
    assert "Region C" in text
    assert "energy" in text and "standing" in text and "VAT" in text
    assert "Jan 2026" in text and "Apr 2026" in text
    assert "SWITCH BACK" in text


def test_format_json_structure():
    data = json.loads(format_json(_result("877.39", "783.83")))
    assert data["recommendation"] == "SWITCH BACK"
    assert data["region"] == "C"
    assert data["tracker"]["product_code"] == "SILVER-26-04-01"
    assert data["flexible_total"] == "877.39"
    assert data["tracker_total"] == "783.83"
    assert len(data["monthly"]) == 2
    assert data["monthly"][0]["flexible"] == "210.40"
    assert data["electricity"]["flexible"]["total"] == "877.39"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_report.py -v`
Expected: FAIL with `ImportError: cannot import name 'MonthlyRow'`.

- [ ] **Step 3: Write minimal implementation**

Replace the entire contents of `src/octopus_compare/report.py` with:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_report.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/octopus_compare/report.py tests/test_report.py
git commit -m "feat: Flexible-vs-Tracker report model + component/monthly formatting"
```

---

### Task 11: Assemble the pipeline (`pipeline.py`)

**Files:**
- Rewrite: `src/octopus_compare/pipeline.py`
- Rewrite: `tests/test_pipeline.py`
- Modify: `tests/fixtures/api_samples.py`

**Interfaces:**
- Consumes: everything above — `parse_account`, `region_letter`, `build_tariff_code`, `resolve_flexible`, `tracker_versions_for_window`, `latest_tracker_version`, `tracker_resolvers`, `fetch_rates`, `fetch_standing_charges`, `fetch_daily`, `to_kwh`, `month_slices`, `supply_cost`, `sum_supply_costs`, `ComparisonResult`, `MonthlyRow`, `TrackerVersion`.
- Produces: `run_comparison(client, config: Config) -> ComparisonResult`.

- [ ] **Step 1: Add fixtures**

Append to `tests/fixtures/api_samples.py`:

```python
# Two-month consumption spanning a month boundary (Mar 30, 31 -> Apr 1).
def _rows(values):
    out = []
    for day, v in values.items():
        out.append({"consumption": v,
                    "interval_start": f"{day}T00:00:00Z",
                    "interval_end": f"{day}T23:30:00Z"})
    return out


ELEC_TWO_MONTH = _rows({"2026-03-30": 9.0, "2026-03-31": 9.0, "2026-04-01": 9.0})
GAS_TWO_MONTH = _rows({"2026-03-30": 30.0, "2026-03-31": 30.0, "2026-04-01": 30.0})
```

- [ ] **Step 2: Write the failing test**

Replace the entire contents of `tests/test_pipeline.py` with:

```python
from datetime import date
from decimal import Decimal

from octopus_compare.config import Config
from octopus_compare.pipeline import run_comparison
from octopus_compare.report import format_text
from tests.fixtures.api_samples import ACCOUNT, ELEC_TWO_MONTH, GAS_TWO_MONTH


class FakeClient:
    """One Tracker version (SILVER-24-12-31, open-ended) and Flexible VAR-22-11-01,
    flat rates, two-month consumption. Tracker is cheaper than Flexible on both
    supplies, so the recommendation is SWITCH BACK."""

    UNIT = {"SILVER": {"electricity": 18.00, "gas": 5.00},
            "VAR": {"electricity": 23.71, "gas": 5.63}}
    STAND = {"SILVER": {"electricity": 37.65, "gas": 28.52},
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
        supply = "electricity" if "electricity" in path else "gas"
        if "consumption" in path:
            return ELEC_TWO_MONTH if supply == "electricity" else GAS_TWO_MONTH
        family = "SILVER" if "SILVER" in path else "VAR"
        table = self.STAND if "standing-charges" in path else self.UNIT
        return [{"value_exc_vat": table[family][supply], "valid_from": None, "valid_to": None}]


def _config():
    return Config(
        api_key="sk", account="A-8F18337C",
        period_from=date(2026, 3, 30), period_to=date(2026, 4, 2),
        output_format="text", gas_calorific_value=Decimal("39.5"),
        gas_units="kwh", verbose=False,
    )


def test_run_comparison_shape_and_aggregation():
    result = run_comparison(FakeClient(), _config())
    # region + latest tracker
    assert result.region == "C"
    assert result.tracker.product_code == "SILVER-24-12-31"
    # two calendar months (March, April)
    assert [row.month for row in result.monthly] == [date(2026, 3, 1), date(2026, 4, 1)]
    assert result.monthly[0].days == 2 and result.monthly[1].days == 1
    # monthly totals sum to the grand totals
    assert sum(r.flexible_pounds for r in result.monthly) == result.flexible_total
    assert sum(r.tracker_pounds for r in result.monthly) == result.tracker_total
    # per-supply totals sum to the grand totals
    assert (result.elec_flexible.total_pounds + result.gas_flexible.total_pounds
            == result.flexible_total)
    # Tracker is cheaper here
    assert result.tracker_total < result.flexible_total


def test_run_comparison_text_renders():
    text = format_text(run_comparison(FakeClient(), _config()))
    assert "SILVER-24-12-31" in text
    assert "Mar 2026" in text and "Apr 2026" in text
    assert "SWITCH BACK" in text
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_pipeline.py -v`
Expected: FAIL (current `run_comparison` returns the old `ComparisonResult` shape — `AttributeError`/`TypeError` on `result.region`/`monthly`).

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
    TrackerVersion,
    _version_from_detail,
)


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
        flex_months[month] = (days, supply_cost(sub, flex_rate_for, flex_sc_for))
        trk_months[month] = (days, supply_cost(sub, trk_rate_for, trk_sc_for))
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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_pipeline.py -v`
Expected: PASS.

- [ ] **Step 6: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS (all offline tests; `test_live_eval.py` is skipped without `OCTOPUS_LIVE_EVAL`).

- [ ] **Step 7: Commit**

```bash
git add src/octopus_compare/pipeline.py tests/test_pipeline.py tests/fixtures/api_samples.py
git commit -m "feat: assemble Flexible-vs-Tracker monthly backtest pipeline"
```

---

### Task 12: Update README usage

**Files:**
- Modify: `README.md`

**Interfaces:** none (docs only).

- [ ] **Step 1: Update the Usage section**

In `README.md`, replace the project description and Usage section so it reflects the new behaviour. Set the description to:

```
Compare what Octopus **Flexible** vs **Tracker** would cost on your real usage,
month by month, and get a switch recommendation. Both columns are pure what-ifs
(your consumption × each tariff's published rates) — neither is your actual bill.
The Tracker side uses the version current each month; the latest version
(today's switch-now rate) is named in the report header.
```

And extend the Usage examples:

```
    octopus-compare                       # last 3 months, Flexible vs latest Tracker
    octopus-compare --from 2026-01-01 --to 2026-05-31   # backtest across your Tracker months
    octopus-compare --tracker-product SILVER-25-09-02   # pin a specific Tracker version
    octopus-compare --region C            # override the auto-derived region
    octopus-compare --format json
```

- [ ] **Step 2: Verify the docs match the CLI**

Run: `python -m octopus_compare.cli --help` (or `octopus-compare --help` if installed)
Expected: the help text lists `--tracker-product` and `--region`.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: README for Flexible-vs-Tracker monthly backtest"
```

---

## Self-Review

**Spec coverage** (each §4–§12 requirement maps to a task):

- Two columns Flexible vs Tracker, pure hypotheticals → Tasks 7, 8, 10, 11.
- Flexible reconstructed by date → Task 7 (resolve) + Task 11 (`_flexible_resolvers`).
- Tracker = current version per day, recent = latest → Tasks 5, 6, 8, 11.
- Component breakdown (energy/standing/VAT) per supply → Task 10 `_block`, fed by Task 11.
- Monthly table + delta + partial-month day count → Task 10 (`_month_label`, monthly loop) + Task 11 (month aggregation).
- Switch-now latest Tracker in header, `--tracker-product` override → Tasks 6, 9, 10, 11.
- Region auto-derived + `--region` override, per supply → Tasks 1, 9, 11.
- Slice & reuse engine, VAT per month, engine untouched → Tasks 2, 3, 11 (engine files unmodified).
- Single-month window == whole-period (eval safety) → engine untouched + `month_slices` yields one bucket; existing `test_costing.py` evals unchanged (Tasks 2–3 run them green).
- JSON mirrors structure → Task 10 `format_json`.
- Discovery 404 fallback, version gap (`KeyError`), bad override code (`ApiError` surfaces) → Tasks 5, 8; surfaced by `cli.main`'s existing `ApiError` handling.

**Placeholder scan:** No TBD/TODO; every code step shows complete code; no "add error handling" hand-waves (errors are concrete `ValueError`/`KeyError`/`ApiError`).

**Type consistency:** `TrackerVersion(product_code, display_name, available_from, available_to)` is defined in Task 5 and used identically in Tasks 6, 8, 10, 11. `SupplyCost` fields match `costing.py`. `MonthlyRow(month, days, flexible_pounds, tracker_pounds)` defined in Task 10, constructed identically in Task 11. `ComparisonResult` field names match between Task 10 (definition) and Task 11 (construction). `build_tariff_code(supply, product_code, region)` signature consistent across Tasks 1, 8, 11. `tracker_resolvers(client, supply, versions, region, period_from, period_to)` consistent between Tasks 8 and 11.

**Edge note for the implementer:** in Task 11, region is derived per supply from that supply's Flexible tariff code, but the result carries the electricity region (`e_region`) — for this household electricity and gas share a region. If a future account differs, this is the documented simplification (the `--region` override forces a single value).
