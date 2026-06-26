# Agile Hour-of-Day Breakdown + Saving Decomposition — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add, to every `octopus-compare agile` run, a structural-vs-behavioural saving decomposition and a 24-row hour-of-day usage-vs-price table, both direction-aware (read correctly whether Agile is cheaper or dearer).

**Architecture:** `agile_resolvers` exposes the Agile rate map it already builds. A new isolated `agile_breakdown.py` computes the decomposition (energy-only, vs a period time-average baseline) and the hour-of-day buckets, reusing the effective prices `AgileInsight` already computes. The pipeline wires it onto `AgileResult`; `report.py` renders it.

**Tech Stack:** Python 3.14, `Decimal` money math, `zoneinfo`, `pytest`.

## Global Constraints

- **Always shown** on every `agile` run; no new flag.
- **Decomposition basis: energy only, excl VAT & standing.** It won't equal the headline total saving (which includes standing + VAT); the output says so.
- **Time-average baseline over ALL period slots**, each half-hour weighted equally — not just consumed slots — so behaviour doesn't bias its own baseline.
- **Period filter:** restrict the rate map to instants in `[period_from 00:00 UTC, period_to 00:00 UTC]` inclusive (drops the `+1` boundary-day rates the upper-boundary fix fetches).
- **`structural_p + behavioural_p == total_p` exactly** (`structural = flex − time_avg`, `behavioural = time_avg − load`, `total = flex − load`).
- **Direction-aware wording:** header / structural / behavioural / net labels flip by sign (cheaper↔dearer, saving↔extra cost). JSON carries raw **signed** numbers.
- **Negatives render with the minus before the `£`** (`-£7.89`, not `£-7.89`).
- **Markers:** `cheap` if hour avg price `< 0.8 × time_avg_p`, `dear` if `> 1.3 × time_avg_p`.
- **No extra API calls** (reuse the rate map from `agile_resolvers`); London-local hour for bucketing; existing tests and the daily report stay green.
- Run tests with `.venv/bin/python -m pytest` from the repo root.

---

### Task 1: `agile_resolvers` returns the rate map

**Files:**
- Modify: `src/octopus_compare/agile.py` (the `agile_resolvers` return)
- Modify: `src/octopus_compare/agile_pipeline.py:58` (unpack three values)
- Test: `tests/test_agile.py` (update the three resolver tests)

**Interfaces:**
- Produces: `agile_resolvers(client, versions, region, period_from, period_to) -> tuple[Callable[[datetime], Decimal], Callable[[date], Decimal], dict[datetime, Decimal]]` — now `(rate_for, sc_for, rate_map)`, where `rate_map` is the merged instant→exc-VAT-pence map.

- [ ] **Step 1: Update the three resolver tests to expect three values**

In `tests/test_agile.py`, change the three `agile_resolvers(...)` call sites:

In `test_agile_resolvers_single_version`:
```python
    rate_for, sc_for, rate_map = agile_resolvers(
        AgileRateClient(), [v], "C", date(2026, 3, 1), date(2026, 3, 2))
    assert rate_for(datetime(2026, 3, 1, 16, 0, tzinfo=_UTC)) == Decimal("21.0")
    assert rate_for(datetime(2026, 3, 1, 13, 30, tzinfo=_UTC)) == Decimal("-2.0")
    assert sc_for(date(2026, 3, 1)) == Decimal("45.0")
    # the merged rate map is returned for analytics
    assert rate_map[datetime(2026, 3, 1, 16, 0, tzinfo=_UTC)] == Decimal("21.0")
```

In `test_agile_resolvers_merges_versions`, change the unpack and add a rate_map assertion:
```python
    rate_for, sc_for, rate_map = agile_resolvers(
        TwoVersionClient(), [v1, v2], "C", date(2024, 1, 1), date(2024, 12, 1))
    # rates from BOTH versions are present in the merged lookup AND the rate map
    assert rate_for(datetime(2024, 1, 15, 0, 0, tzinfo=_UTC)) == Decimal("12.0")
    assert rate_for(datetime(2024, 11, 15, 0, 0, tzinfo=_UTC)) == Decimal("25.0")
    assert rate_map[datetime(2024, 1, 15, 0, 0, tzinfo=_UTC)] == Decimal("12.0")
    assert rate_map[datetime(2024, 11, 15, 0, 0, tzinfo=_UTC)] == Decimal("25.0")
    # standing charge selected per version by date
    assert sc_for(date(2024, 1, 15)) == Decimal("30.0")
    assert sc_for(date(2024, 11, 15)) == Decimal("45.0")
```

In `test_agile_resolvers_cover_period_to_boundary_instant`, change the unpack:
```python
    rate_for, _sc, _map = agile_resolvers(
        BoundaryAwareClient(), [v], "C", date(2026, 5, 28), date(2026, 5, 30))
```

- [ ] **Step 2: Run the resolver tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_agile.py -k resolvers -v`
Expected: FAIL — `ValueError: not enough values to unpack (expected 3, got 2)`

- [ ] **Step 3: Return the rate map from `agile_resolvers`**

In `src/octopus_compare/agile.py`, change the final line of `agile_resolvers`:

```python
    return HalfHourlyRates(by_instant).rate_for, VersionedLookup(sc_entries).rate_for, by_instant
```

And update its docstring's first line to: `"""(rate_for, sc_for, rate_map) for the Agile column. ..."""` (keep the rest).

- [ ] **Step 4: Update the pipeline unpack so the suite stays green**

In `src/octopus_compare/agile_pipeline.py`, change line 58:

```python
    agile_rate_for, agile_sc_for, agile_rate_map = agile_resolvers(
        client, versions, region, config.period_from, config.period_to)
```

(`agile_rate_map` is unused until Task 5 — that's intentional.)

- [ ] **Step 5: Run tests to verify green**

Run: `.venv/bin/python -m pytest tests/test_agile.py tests/test_agile_pipeline.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/octopus_compare/agile.py src/octopus_compare/agile_pipeline.py tests/test_agile.py
git commit -m "refactor: agile_resolvers returns the merged rate map for analytics"
```

---

### Task 2: Decomposition

**Files:**
- Create: `src/octopus_compare/agile_breakdown.py`
- Test: `tests/test_agile_breakdown.py`

**Interfaces:**
- Consumes: `pounds` from `octopus_compare.money`.
- Produces: `Decomposition(flex_p, time_avg_p, load_p, structural_p, behavioural_p, total_p, structural_pounds, behavioural_pounds, total_pounds, total_kwh)` (all `Decimal`); `_period_rates(rate_map, period_from, period_to) -> dict[datetime, Decimal]`; `compute_decomposition(period_rates: dict[datetime, Decimal], flex_effective_p: Decimal, agile_effective_p: Decimal, total_kwh: Decimal) -> Decomposition`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_agile_breakdown.py`:

```python
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from octopus_compare.agile_breakdown import (
    _period_rates, compute_decomposition)

UTC = ZoneInfo("UTC")


def test_decomposition_algebra_and_pounds():
    period_rates = {
        datetime(2026, 3, 1, 0, 0, tzinfo=UTC): Decimal("10"),
        datetime(2026, 3, 1, 0, 30, tzinfo=UTC): Decimal("20"),
        datetime(2026, 3, 1, 1, 0, tzinfo=UTC): Decimal("20"),
        datetime(2026, 3, 1, 1, 30, tzinfo=UTC): Decimal("30"),
    }  # mean = 20
    d = compute_decomposition(period_rates, Decimal("24.0"), Decimal("22.0"), Decimal("100"))
    assert d.time_avg_p == Decimal("20.0")
    assert d.structural_p == Decimal("4.0")      # 24.0 - 20.0  (Agile cheaper on avg)
    assert d.behavioural_p == Decimal("-2.0")    # 20.0 - 22.0  (you use at dearer times)
    assert d.total_p == Decimal("2.0")           # 24.0 - 22.0
    assert d.structural_p + d.behavioural_p == d.total_p
    assert d.structural_pounds == Decimal("4.00")     # 4.0 * 100 / 100
    assert d.behavioural_pounds == Decimal("-2.00")
    assert d.total_pounds == Decimal("2.00")
    assert d.total_kwh == Decimal("100")


def test_decomposition_inverse_agile_dearer():
    period_rates = {datetime(2026, 3, 1, 0, 0, tzinfo=UTC): Decimal("28")}
    d = compute_decomposition(period_rates, Decimal("24.0"), Decimal("30.0"), Decimal("100"))
    assert d.time_avg_p == Decimal("28.0")
    assert d.structural_p == Decimal("-4.0")     # Agile DEARER on average
    assert d.behavioural_p == Decimal("-2.0")
    assert d.total_p == Decimal("-6.0")          # Agile dearer overall
    assert d.total_pounds == Decimal("-6.00")


def test_period_filter_excludes_boundary_day():
    rate_map = {
        datetime(2026, 5, 28, 0, 0, tzinfo=UTC): Decimal("10"),
        datetime(2026, 5, 30, 0, 0, tzinfo=UTC): Decimal("12"),   # == period_to, kept
        datetime(2026, 5, 31, 0, 0, tzinfo=UTC): Decimal("99"),   # +1 day, dropped
    }
    pr = _period_rates(rate_map, date(2026, 5, 28), date(2026, 5, 30))
    assert datetime(2026, 5, 30, 0, 0, tzinfo=UTC) in pr
    assert datetime(2026, 5, 31, 0, 0, tzinfo=UTC) not in pr
    assert len(pr) == 2
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_agile_breakdown.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'octopus_compare.agile_breakdown'`

- [ ] **Step 3: Implement**

Create `src/octopus_compare/agile_breakdown.py`:

```python
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from octopus_compare.money import pounds

_LONDON = ZoneInfo("Europe/London")
_UTC = ZoneInfo("UTC")


def _period_rates(rate_map: dict[datetime, Decimal], period_from: date,
                  period_to: date) -> dict[datetime, Decimal]:
    """rate_map restricted to instants in [period_from 00:00 UTC, period_to 00:00
    UTC] inclusive — the requested window, excluding the +1 boundary-day rates."""
    start = datetime(period_from.year, period_from.month, period_from.day, tzinfo=_UTC)
    end = datetime(period_to.year, period_to.month, period_to.day, tzinfo=_UTC)
    return {i: r for i, r in rate_map.items() if start <= i <= end}


@dataclass
class Decomposition:
    flex_p: Decimal             # Flexible effective unit price, exc-VAT p/kWh
    time_avg_p: Decimal         # Agile time-average (flat-user) price
    load_p: Decimal             # Agile load-weighted (actual) price
    structural_p: Decimal       # flex_p - time_avg_p  (>0: Agile cheaper on avg)
    behavioural_p: Decimal      # time_avg_p - load_p  (>0: you use at cheaper times)
    total_p: Decimal            # flex_p - load_p
    structural_pounds: Decimal  # over the period (signed)
    behavioural_pounds: Decimal
    total_pounds: Decimal
    total_kwh: Decimal


def compute_decomposition(period_rates: dict[datetime, Decimal],
                          flex_effective_p: Decimal, agile_effective_p: Decimal,
                          total_kwh: Decimal) -> Decomposition:
    if period_rates:
        time_avg = (sum(period_rates.values(), Decimal(0)) / len(period_rates)).quantize(Decimal("0.1"))
    else:
        time_avg = Decimal(0)
    structural = flex_effective_p - time_avg
    behavioural = time_avg - agile_effective_p
    total = flex_effective_p - agile_effective_p
    return Decomposition(
        flex_p=flex_effective_p, time_avg_p=time_avg, load_p=agile_effective_p,
        structural_p=structural, behavioural_p=behavioural, total_p=total,
        structural_pounds=pounds(structural * total_kwh),
        behavioural_pounds=pounds(behavioural * total_kwh),
        total_pounds=pounds(total * total_kwh),
        total_kwh=total_kwh,
    )
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_agile_breakdown.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/octopus_compare/agile_breakdown.py tests/test_agile_breakdown.py
git commit -m "feat: structural-vs-behavioural saving decomposition"
```

---

### Task 3: Hour-of-day buckets + summary

**Files:**
- Modify: `src/octopus_compare/agile_breakdown.py`
- Test: `tests/test_agile_breakdown.py`

**Interfaces:**
- Consumes: `Decimal`, `_LONDON` (already in the module).
- Produces: `HourBucket(hour: int, usage_pct: Decimal, avg_price_p: Decimal, marker: str | None)`; `compute_hours(halfhourly_kwh: dict[datetime, Decimal], period_rates: dict[datetime, Decimal], total_kwh: Decimal, time_avg_p: Decimal) -> tuple[list[HourBucket], Decimal, Decimal]` — `(by_hour[24], cheapest6_usage_pct, dearest6_usage_pct)`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_agile_breakdown.py`:

```python
from octopus_compare.agile_breakdown import compute_hours, HourBucket


def test_compute_hours_buckets_and_markers():
    hh = {datetime(2026, 3, 1, 14, 0, tzinfo=UTC): Decimal("1"),
          datetime(2026, 3, 1, 18, 0, tzinfo=UTC): Decimal("1")}
    period_rates = {datetime(2026, 3, 1, 14, 0, tzinfo=UTC): Decimal("5"),
                    datetime(2026, 3, 1, 18, 0, tzinfo=UTC): Decimal("40")}
    buckets, _c, _d = compute_hours(hh, period_rates, Decimal("2"), Decimal("22.5"))
    assert len(buckets) == 24
    assert buckets[14].usage_pct == Decimal("50.0")
    assert buckets[14].avg_price_p == Decimal("5.0")
    assert buckets[14].marker == "cheap"        # 5 < 22.5*0.8 = 18
    assert buckets[18].marker == "dear"         # 40 > 22.5*1.3 = 29.25
    assert buckets[0].avg_price_p == Decimal("0")  # no slots that hour
    assert buckets[0].marker is None


def test_compute_hours_summary_shares():
    # hours 0..11 priced 1..12p; all usage in hour 11 (the dearest)
    period_rates = {datetime(2026, 3, 1, h, 0, tzinfo=UTC): Decimal(h + 1) for h in range(12)}
    hh = {datetime(2026, 3, 1, 11, 0, tzinfo=UTC): Decimal("1")}
    _b, cheap6, dear6 = compute_hours(hh, period_rates, Decimal("1"), Decimal("6.5"))
    assert dear6 == Decimal("100.0")     # hours 6..11 are the dearest 6; usage is in 11
    assert cheap6 == Decimal("0.0")      # hours 0..5 are the cheapest 6; no usage there
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_agile_breakdown.py -k hours -v`
Expected: FAIL — `ImportError: cannot import name 'compute_hours'`

- [ ] **Step 3: Implement**

Add to `src/octopus_compare/agile_breakdown.py`:

```python
@dataclass
class HourBucket:
    hour: int                 # London-local hour 0-23
    usage_pct: Decimal        # % of total kWh used in this hour
    avg_price_p: Decimal      # mean Agile price in this hour (exc-VAT p/kWh)
    marker: str | None        # "cheap" | "dear" | None


def compute_hours(halfhourly_kwh: dict[datetime, Decimal],
                  period_rates: dict[datetime, Decimal], total_kwh: Decimal,
                  time_avg_p: Decimal) -> tuple[list, Decimal, Decimal]:
    usage = {h: Decimal(0) for h in range(24)}
    for instant, kwh in halfhourly_kwh.items():
        usage[instant.astimezone(_LONDON).hour] += Decimal(kwh)
    prices: dict[int, list] = {h: [] for h in range(24)}
    for instant, rate in period_rates.items():
        prices[instant.astimezone(_LONDON).hour].append(rate)

    cheap_thresh = time_avg_p * Decimal("0.8")
    dear_thresh = time_avg_p * Decimal("1.3")
    buckets = []
    for h in range(24):
        pct = (usage[h] / total_kwh * 100).quantize(Decimal("0.1")) if total_kwh else Decimal(0)
        if prices[h]:
            avg = (sum(prices[h], Decimal(0)) / len(prices[h])).quantize(Decimal("0.1"))
            marker = "cheap" if avg < cheap_thresh else "dear" if avg > dear_thresh else None
        else:
            avg, marker = Decimal(0), None
        buckets.append(HourBucket(h, pct, avg, marker))

    priced = sorted((b for b in buckets if prices[b.hour]), key=lambda b: b.avg_price_p)
    cheapest6 = sum((b.usage_pct for b in priced[:6]), Decimal(0))
    dearest6 = sum((b.usage_pct for b in priced[-6:]), Decimal(0))
    return buckets, cheapest6, dearest6
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_agile_breakdown.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/octopus_compare/agile_breakdown.py tests/test_agile_breakdown.py
git commit -m "feat: hour-of-day usage/price buckets with cheap/dear markers + summary"
```

---

### Task 4: `AgileBreakdown` + `compute_breakdown` orchestrator

**Files:**
- Modify: `src/octopus_compare/agile_breakdown.py`
- Test: `tests/test_agile_breakdown.py`

**Interfaces:**
- Consumes: `_period_rates`, `compute_decomposition`, `compute_hours` (this module).
- Produces: `AgileBreakdown(decomposition: Decomposition, by_hour: list, cheapest6_usage_pct: Decimal, dearest6_usage_pct: Decimal)`; `compute_breakdown(halfhourly_kwh: dict[datetime, Decimal], rate_map: dict[datetime, Decimal], flex_effective_p: Decimal, agile_effective_p: Decimal, total_kwh: Decimal, period_from: date, period_to: date) -> AgileBreakdown`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_agile_breakdown.py`:

```python
from octopus_compare.agile_breakdown import compute_breakdown, AgileBreakdown


def test_compute_breakdown_integrates():
    rate_map = {
        datetime(2026, 3, 1, 0, 0, tzinfo=UTC): Decimal("20"),
        datetime(2026, 3, 2, 0, 0, tzinfo=UTC): Decimal("99"),  # +1 day, filtered out
    }
    hh = {datetime(2026, 3, 1, 0, 0, tzinfo=UTC): Decimal("1")}
    b = compute_breakdown(hh, rate_map, Decimal("24.0"), Decimal("20.0"),
                          Decimal("1"), date(2026, 3, 1), date(2026, 3, 1))
    assert isinstance(b, AgileBreakdown)
    assert len(b.by_hour) == 24
    assert b.decomposition.time_avg_p == Decimal("20.0")   # 99 excluded by the filter
    assert b.decomposition.structural_p + b.decomposition.behavioural_p == b.decomposition.total_p
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_agile_breakdown.py -k breakdown -v`
Expected: FAIL — `ImportError: cannot import name 'compute_breakdown'`

- [ ] **Step 3: Implement**

Add to `src/octopus_compare/agile_breakdown.py`:

```python
@dataclass
class AgileBreakdown:
    decomposition: Decomposition
    by_hour: list                 # list[HourBucket], 24 entries hour 0-23
    cheapest6_usage_pct: Decimal
    dearest6_usage_pct: Decimal


def compute_breakdown(halfhourly_kwh: dict[datetime, Decimal],
                      rate_map: dict[datetime, Decimal], flex_effective_p: Decimal,
                      agile_effective_p: Decimal, total_kwh: Decimal,
                      period_from: date, period_to: date) -> AgileBreakdown:
    period_rates = _period_rates(rate_map, period_from, period_to)
    decomp = compute_decomposition(period_rates, flex_effective_p, agile_effective_p, total_kwh)
    by_hour, cheap6, dear6 = compute_hours(halfhourly_kwh, period_rates, total_kwh, decomp.time_avg_p)
    return AgileBreakdown(decomp, by_hour, cheap6, dear6)
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_agile_breakdown.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/octopus_compare/agile_breakdown.py tests/test_agile_breakdown.py
git commit -m "feat: compute_breakdown orchestrator returning AgileBreakdown"
```

---

### Task 5: Wire breakdown into the pipeline and the report

**Files:**
- Modify: `src/octopus_compare/report.py` (AgileResult field + renderers + JSON)
- Modify: `src/octopus_compare/agile_pipeline.py` (compute + pass breakdown)
- Test: `tests/test_agile_report.py`, `tests/test_agile_pipeline.py`

**Interfaces:**
- Consumes: `AgileBreakdown`, `Decomposition`, `HourBucket` (`agile_breakdown.py`); `compute_breakdown`; the `agile_rate_map` from Task 1; `insight.flex_effective_p` / `insight.agile_effective_p` (`AgileInsight`).
- Produces: `AgileResult` gains required field `breakdown: AgileBreakdown`. `format_agile_text` / `format_agile_json` render it.

- [ ] **Step 1: Write the failing report + pipeline tests**

In `tests/test_agile_report.py`, add imports and a breakdown helper near the top (after the existing imports):

```python
from octopus_compare.agile_breakdown import AgileBreakdown, Decomposition, HourBucket


def _breakdown(structural="7.1", behavioural="-1.3", total="5.8"):
    decomp = Decomposition(
        flex_p=Decimal("24.0"), time_avg_p=Decimal("16.9"), load_p=Decimal("18.2"),
        structural_p=Decimal(structural), behavioural_p=Decimal(behavioural),
        total_p=Decimal(total),
        structural_pounds=Decimal("43.85"), behavioural_pounds=Decimal("-7.89"),
        total_pounds=Decimal("35.95"), total_kwh=Decimal("622"))
    hours = [HourBucket(h, Decimal("4.0"), Decimal("15.0"), None) for h in range(24)]
    hours[14] = HourBucket(14, Decimal("4.8"), Decimal("10.2"), "cheap")
    hours[18] = HourBucket(18, Decimal("9.4"), Decimal("32.5"), "dear")
    return AgileBreakdown(decomp, hours, Decimal("29.0"), Decimal("41.0"))
```

Update the existing `_result(...)` helper to pass a breakdown (find the `AgileResult(` constructor in it and add the field):
```python
        insight=_insight(),
        breakdown=_breakdown())
```

Add these tests:
```python
def test_format_agile_text_has_decomposition_cheaper():
    text = format_agile_text(_result("286.80", "234.64"))
    assert "Why Agile is cheaper" in text
    assert "Agile if you used power evenly" in text
    assert "Structural (Agile cheaper on average)" in text
    assert "Net saving" in text
    assert "-£7.89" in text                 # minus before the £
    assert "Hour-of-day (London)" in text
    assert "Usage in 6 cheapest hours: 29.0%" in text


def test_format_agile_text_decomposition_inverse():
    res = _result("234.64", "286.80")       # Agile dearer overall
    res.breakdown = _breakdown(structural="-4.0", behavioural="-2.0", total="-6.0")
    text = format_agile_text(res)
    assert "Why Agile is more expensive" in text
    assert "Agile dearer on average" in text
    assert "you use at dearer times" in text
    assert "Net extra cost" in text


def test_format_agile_json_has_breakdown():
    data = json.loads(format_agile_json(_result("286.80", "234.64")))
    assert data["breakdown"]["decomposition"]["structural_p"] == "7.1"
    assert data["breakdown"]["decomposition"]["total_pounds"] == "35.95"
    assert len(data["breakdown"]["by_hour"]) == 24
    assert data["breakdown"]["by_hour"][18]["marker"] == "dear"
    assert data["breakdown"]["cheapest6_usage_pct"] == "29.0"
```

In `tests/test_agile_pipeline.py`, add:
```python
def test_run_agile_comparison_populates_breakdown():
    result = run_agile_comparison(AgileFakeClient(), _config())
    b = result.breakdown
    assert len(b.by_hour) == 24
    assert b.decomposition.structural_p + b.decomposition.behavioural_p == b.decomposition.total_p
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_agile_report.py tests/test_agile_pipeline.py -v`
Expected: FAIL — `TypeError: __init__() missing 1 required positional argument: 'breakdown'` (and the new asserts).

- [ ] **Step 3: Add the `breakdown` field + renderers to `report.py`**

In `src/octopus_compare/report.py`, add to the imports near `from octopus_compare.agile_insight import AgileInsight`:
```python
from octopus_compare.agile_breakdown import AgileBreakdown
```

Add the field to `AgileResult` (after `insight: AgileInsight`):
```python
    breakdown: AgileBreakdown
```

Add these helpers (place them just before `format_agile_text`):
```python
def _signed_p(v: Decimal) -> str:
    return f"+{v}" if v > 0 else f"-{abs(v)}" if v < 0 else f"{v}"


def _signed_pounds(v: Decimal) -> str:
    return f"-£{abs(v)}" if v < 0 else f"£{v}"


def _agile_decomposition_lines(d) -> list[str]:
    header = ("Why Agile is cheaper" if d.total_p > 0
              else "Why Agile is more expensive" if d.total_p < 0
              else "Flexible vs Agile — energy breakdown")
    struct = ("Agile cheaper on average" if d.structural_p > 0
              else "Agile dearer on average" if d.structural_p < 0
              else "Agile same on average")
    behav = ("you use at cheaper times" if d.behavioural_p > 0
             else "you use at dearer times" if d.behavioural_p < 0
             else "your timing is neutral")
    net = ("Net saving" if d.total_p > 0
           else "Net extra cost" if d.total_p < 0 else "Net: no difference")
    return [
        f"{header} (energy only, excl VAT & standing)",
        f"  Flexible flat rate                 {d.flex_p} p/kWh",
        f"  Agile if you used power evenly     {d.time_avg_p} p/kWh   (time-average)",
        f"  Agile on your actual usage         {d.load_p} p/kWh   (your load)",
        "  ──────────────────────────────────────────────",
        f"  Structural ({struct})  {_signed_p(d.structural_p)} p/kWh   {_signed_pounds(d.structural_pounds)}",
        f"  Behavioural ({behav})  {_signed_p(d.behavioural_p)} p/kWh   {_signed_pounds(d.behavioural_pounds)}",
        f"  {net}  {_signed_p(d.total_p)} p/kWh   {_signed_pounds(d.total_pounds)}",
        "",
    ]


def _agile_hour_lines(b) -> list[str]:
    lines = ["Hour-of-day (London)       usage   avg Agile"]
    for hb in b.by_hour:
        bar = "█" * round(hb.usage_pct / Decimal("0.5"))
        mark = "  cheap" if hb.marker == "cheap" else "  DEAR" if hb.marker == "dear" else ""
        lines.append(f"  {hb.hour:02d}:00  {hb.usage_pct:>5}%   {hb.avg_price_p:>5}p  {bar}{mark}")
    lines.append(f"  Usage in 6 cheapest hours: {b.cheapest6_usage_pct}% · "
                 f"6 dearest: {b.dearest6_usage_pct}%  (flat user: 25% / 25%)")
    lines.append("")
    return lines
```

Wire them into `format_agile_text` — replace the two lines:
```python
    lines += _agile_insight_lines(result.insight)
    lines += _agile_reco_lines(result)
```
with:
```python
    lines += _agile_insight_lines(result.insight)
    lines += _agile_decomposition_lines(result.breakdown.decomposition)
    lines += _agile_hour_lines(result.breakdown)
    lines += _agile_reco_lines(result)
```

In `format_agile_json`, add a `breakdown` key. Insert it immediately before the `"recommendation": recommend_agile(result),` line:
```python
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
```

- [ ] **Step 4: Compute and pass the breakdown in the pipeline**

In `src/octopus_compare/agile_pipeline.py`, add the import:
```python
from octopus_compare.agile_breakdown import compute_breakdown
```

Replace the `insight = ...` + `return AgileResult(...)` tail of `run_agile_comparison` with:
```python
    insight = compute_insight(hh, agile_rate_for, flex_rate_for, config.peak_window)
    breakdown = compute_breakdown(
        hh, agile_rate_map, insight.flex_effective_p, insight.agile_effective_p,
        elec_agile.consumption_kwh, config.period_from, config.period_to)

    return AgileResult(
        period_from=config.period_from, period_to=config.period_to, region=region,
        agile_versions=versions,
        elec_flexible=elec_flex, elec_agile=elec_agile,
        monthly=monthly, insight=insight, breakdown=breakdown,
    )
```

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest`
Expected: PASS (the new report/pipeline tests plus everything pre-existing; the daily report is untouched).

- [ ] **Step 6: Commit**

```bash
git add src/octopus_compare/report.py src/octopus_compare/agile_pipeline.py tests/test_agile_report.py tests/test_agile_pipeline.py
git commit -m "feat: render the saving decomposition + hour-of-day breakdown in the agile report"
```

---

### Task 6: README

**Files:**
- Modify: `README.md`

**Interfaces:** none (docs only).

- [ ] **Step 1: Update the README**

In `README.md`, in the paragraph describing `octopus-compare agile`, extend the sentence listing what the insight block shows to also mention: "plus a breakdown of *why* Agile is cheaper or dearer — splitting the difference into a **structural** part (Agile's average price vs the Flexible flat rate) and a **behavioural** part (whether your usage falls at cheaper- or dearer-than-average times) — and an hour-of-day table of usage vs price."

- [ ] **Step 2: Verify the suite is still green**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS (docs-only change; no test impact).

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: README for the agile saving decomposition + hour-of-day breakdown"
```

---

## Self-Review

**Spec coverage:**
- §3 plumbing (`agile_resolvers` returns rate_map) → Task 1.
- §3 new module + dataclasses → Tasks 2 (Decomposition), 3 (HourBucket), 4 (AgileBreakdown).
- §4 period filter → Task 2 (`_period_rates`, tested). Decomposition math → Task 2. Hour buckets + markers + summary → Task 3.
- §3 pipeline wiring + §3 report field/renderers → Task 5.
- §5 output (direction-aware text, signed values, `-£` ordering, JSON `breakdown`) → Task 5 (`_agile_decomposition_lines`, `_agile_hour_lines`, JSON block) with cheaper + inverse tests.
- §6 testing (algebra, inverse, period filter, buckets, markers, summary, resolver 3-tuple, pipeline populate, report cheaper/inverse/json) → Tasks 1–5.
- §2 always-shown / energy-only → Task 5 wiring (no flag) + the header copy "(energy only, excl VAT & standing)".
- README → Task 6.

**Placeholder scan:** No TBD/TODO; every code step carries complete code. The `_result` helper edit in Task 5 names the exact lines to add.

**Type consistency:** `agile_resolvers` returns `(rate_for, sc_for, rate_map)` (Task 1) consumed as `agile_rate_map` in Task 5. `compute_decomposition` (Task 2) → `Decomposition` consumed by `compute_breakdown` (Task 4) and rendered in Task 5. `compute_hours` (Task 3) returns `(list[HourBucket], Decimal, Decimal)` consumed by `compute_breakdown` (Task 4). `compute_breakdown(halfhourly_kwh, rate_map, flex_effective_p, agile_effective_p, total_kwh, period_from, period_to)` (Task 4) is called with exactly those args in Task 5. `AgileResult.breakdown: AgileBreakdown` (Task 5) matches what the pipeline constructs. Signed-render helpers (`_signed_p`/`_signed_pounds`) defined and used only in Task 5.
