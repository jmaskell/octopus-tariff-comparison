# Honest Tariff Comparison Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop `octopus-compare` from presenting analysis that can push the user to the wrong tariff — separate the time-bases, suppress verdicts on bad/ambiguous data, and never declare a winner inside the noise.

**Architecture:** Two new pure modules (`verdict.py`, `coverage.py`) provide the tie-band decision and data-coverage detection. `consumption.py` gains a confidence flag for gas-unit auto-detection. The 3-way report is reframed into a same-basis Flexible-vs-Tracker backtest plus a clearly-separated forward Fixed lock-in check; the Agile report's decomposition is reconciled to the actual bill. All verdicts are suppressed (tables still shown) when coverage is incomplete or gas units are ambiguous, unless `--allow-partial-data` is set.

**Tech Stack:** Python 3.14, `decimal.Decimal` throughout, `pytest`. No new dependencies.

## Global Constraints

- All money/rates are `Decimal`; never float. Pence rounding is `ROUND_HALF_UP` via `money.round_pence`; pounds via `money.pounds`.
- Spec: `docs/superpowers/specs/2026-06-26-honest-comparison-design.md`.
- Run tests with `./.venv/bin/python -m pytest` (RTK filters plain `python -m pytest`).
- Tie band: a challenger beats the other only if the gap is **> 2% of the cheaper total AND > £5**; else `TOO_CLOSE`. Band constants live in `verdict.py`.
- Gas ambiguous band: mean daily raw in `[4, 25)` → not confident. Constants in `consumption.py`.
- Agile divergence threshold: Σ half-hourly vs Σ daily kWh differing by > 2% → suspect.
- JSON output shape is allowed to change (single-user tool).
- Commit after every green step. Work stays on branch `fix/honest-comparison`.

---

### Task 1: `verdict.py` — tie-band decision

**Files:**
- Create: `src/octopus_compare/verdict.py`
- Test: `tests/test_verdict.py`

**Interfaces:**
- Produces: `class Verdict(str, Enum)` with members `STAY`, `SWITCH`, `TOO_CLOSE`; `decide(status_quo: Decimal, challenger: Decimal, pct: Decimal = Decimal("2"), abs_pounds: Decimal = Decimal("5")) -> Verdict`. `SWITCH` means the challenger is clearly cheaper; `STAY` means the status quo is clearly cheaper; `TOO_CLOSE` means within band.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_verdict.py
from decimal import Decimal

from octopus_compare.verdict import Verdict, decide


def test_clear_switch_when_challenger_well_below():
    assert decide(Decimal("1000"), Decimal("950")) == Verdict.SWITCH


def test_clear_stay_when_status_quo_well_below():
    assert decide(Decimal("950"), Decimal("1000")) == Verdict.STAY


def test_too_close_when_gap_under_abs_floor():
    # £0.50 gap, well over 2% would need £19 — fails abs floor anyway
    assert decide(Decimal("1080.00"), Decimal("1080.50")) == Verdict.TOO_CLOSE


def test_too_close_when_gap_over_fiver_but_under_two_pct():
    # £8 gap on ~£812 is 0.99% < 2% -> too close despite clearing £5
    assert decide(Decimal("812"), Decimal("820")) == Verdict.TOO_CLOSE


def test_switch_needs_both_pct_and_abs():
    # £40 on £1000 = 4% and > £5 -> clear
    assert decide(Decimal("1040"), Decimal("1000")) == Verdict.SWITCH


def test_small_bill_blocked_by_abs_floor():
    # £4 gap on £100 = 4% (clears pct) but < £5 -> too close
    assert decide(Decimal("104"), Decimal("100")) == Verdict.TOO_CLOSE
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_verdict.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'octopus_compare.verdict'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/octopus_compare/verdict.py
from decimal import Decimal
from enum import Enum


class Verdict(str, Enum):
    STAY = "STAY"
    SWITCH = "SWITCH"
    TOO_CLOSE = "TOO_CLOSE"


def decide(
    status_quo: Decimal,
    challenger: Decimal,
    pct: Decimal = Decimal("2"),
    abs_pounds: Decimal = Decimal("5"),
) -> Verdict:
    """Compare a challenger total against the status-quo total.

    The challenger 'wins' (SWITCH) only if it is cheaper by more than `pct`%
    of the cheaper of the two AND by more than `abs_pounds`. Symmetrically the
    status quo 'wins' (STAY). Anything inside the band is TOO_CLOSE.
    """
    gap = status_quo - challenger  # >0 => challenger cheaper
    cheaper = min(status_quo, challenger)
    clear = abs(gap) > (pct / 100 * cheaper) and abs(gap) > abs_pounds
    if not clear:
        return Verdict.TOO_CLOSE
    return Verdict.SWITCH if gap > 0 else Verdict.STAY
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/bin/python -m pytest tests/test_verdict.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add src/octopus_compare/verdict.py tests/test_verdict.py
git commit -m "feat: tie-band verdict helper (>2% AND >£5 to win)"
```

---

### Task 2: `coverage.py` — data-coverage detection

**Files:**
- Create: `src/octopus_compare/coverage.py`
- Test: `tests/test_coverage.py`

**Interfaces:**
- Produces:
  - `@dataclass SupplyCoverage` `{supply: str, priced_days: int, expected_days: int, missing_months: list[date]}`
  - `@dataclass Coverage` `{per_supply: list[SupplyCoverage], notes: list[str]}` with property `complete: bool` (True iff every supply has `priced_days >= expected_days` and `notes` is empty).
  - `compare_coverage(period_from: date, period_to: date, priced_days_by_supply: dict[str, set[date]]) -> Coverage`
  - `@dataclass AgileCoverage` `{daily_days: int, hh_days: int, missing_hh_days: list[date], daily_kwh: Decimal, hh_kwh: Decimal, divergence_pct: Decimal, notes: list[str]}` with property `complete: bool` (True iff `missing_hh_days` empty and `notes` empty).
  - `agile_coverage(daily_days: set[date], hh_local_days: set[date], daily_kwh: Decimal, hh_kwh: Decimal, divergence_threshold: Decimal = Decimal("2")) -> AgileCoverage`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_coverage.py
from datetime import date
from decimal import Decimal

from octopus_compare.coverage import (
    compare_coverage,
    agile_coverage,
)


def _days(y, m, d_start, d_end):
    return {date(y, m, d) for d in range(d_start, d_end + 1)}


def test_full_coverage_is_complete():
    elec = _days(2026, 1, 1, 31)
    gas = _days(2026, 1, 1, 31)
    cov = compare_coverage(date(2026, 1, 1), date(2026, 2, 1),
                           {"electricity": elec, "gas": gas})
    assert cov.complete
    assert all(s.priced_days == s.expected_days == 31 for s in cov.per_supply)


def test_trailing_unsettled_days_do_not_trip():
    # window asks to 31 Jan but both supplies only have data to the 28th
    elec = _days(2026, 1, 1, 28)
    gas = _days(2026, 1, 1, 28)
    cov = compare_coverage(date(2026, 1, 1), date(2026, 2, 1),
                           {"electricity": elec, "gas": gas})
    assert cov.complete  # expected trimmed to the 28th


def test_internal_gap_in_one_supply_flags_incomplete():
    elec = _days(2026, 1, 1, 31)
    gas = _days(2026, 1, 1, 31) - _days(2026, 1, 10, 15)  # 6-day hole
    cov = compare_coverage(date(2026, 1, 1), date(2026, 2, 1),
                           {"electricity": elec, "gas": gas})
    assert not cov.complete
    gas_cov = next(s for s in cov.per_supply if s.supply == "gas")
    assert gas_cov.priced_days == 25
    assert gas_cov.expected_days == 31
    assert date(2026, 1, 1) in gas_cov.missing_months


def test_cross_supply_span_mismatch_flags_gas():
    elec = _days(2026, 1, 1, 31)
    gas = _days(2026, 1, 16, 31)  # gas only second half
    cov = compare_coverage(date(2026, 1, 1), date(2026, 2, 1),
                           {"electricity": elec, "gas": gas})
    assert not cov.complete
    gas_cov = next(s for s in cov.per_supply if s.supply == "gas")
    assert gas_cov.priced_days == 16
    assert gas_cov.expected_days == 31


def test_no_data_at_all_has_note():
    cov = compare_coverage(date(2026, 1, 1), date(2026, 2, 1),
                           {"electricity": set(), "gas": set()})
    assert not cov.complete
    assert cov.notes


def test_agile_complete_when_hh_covers_daily():
    daily = _days(2026, 1, 1, 10)
    hh = _days(2026, 1, 1, 10)
    cov = agile_coverage(daily, hh, Decimal("100"), Decimal("100"))
    assert cov.complete


def test_agile_missing_hh_day_flags():
    daily = _days(2026, 1, 1, 10)
    hh = _days(2026, 1, 1, 10) - {date(2026, 1, 5)}
    cov = agile_coverage(daily, hh, Decimal("100"), Decimal("90"))
    assert not cov.complete
    assert date(2026, 1, 5) in cov.missing_hh_days


def test_agile_divergence_flags_even_with_all_days():
    daily = _days(2026, 1, 1, 10)
    hh = _days(2026, 1, 1, 10)
    cov = agile_coverage(daily, hh, Decimal("100"), Decimal("80"))  # 20% off
    assert not cov.complete
    assert cov.divergence_pct == Decimal("20.0")
    assert cov.notes
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_coverage.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'octopus_compare.coverage'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/octopus_compare/coverage.py
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal


@dataclass
class SupplyCoverage:
    supply: str
    priced_days: int
    expected_days: int
    missing_months: list[date]


@dataclass
class Coverage:
    per_supply: list[SupplyCoverage]
    notes: list[str]

    @property
    def complete(self) -> bool:
        return (
            not self.notes
            and all(s.priced_days >= s.expected_days for s in self.per_supply)
        )


def _days(start: date, end: date):
    """Yield each date in [start, end)."""
    d = start
    while d < end:
        yield d
        d += timedelta(days=1)


def compare_coverage(
    period_from: date,
    period_to: date,
    priced_days_by_supply: dict[str, set[date]],
) -> Coverage:
    """Coverage for the 3-way compare.

    `expected` is the requested window [period_from, period_to) trimmed to the
    span actually backed by data on at least one supply (so unsettled recent
    days, and a not-yet-started leading edge, never count as missing). A supply
    is short if it lacks any day inside that shared span.
    """
    in_window = {
        d
        for days in priced_days_by_supply.values()
        for d in days
        if period_from <= d < period_to
    }
    if not in_window:
        per = [
            SupplyCoverage(s, 0, 0, []) for s in priced_days_by_supply
        ]
        return Coverage(per, ["no consumption data in the requested window"])

    span_start, span_end = min(in_window), max(in_window)
    expected = set(_days(span_start, span_end + timedelta(days=1)))

    per_supply = []
    for supply, days in priced_days_by_supply.items():
        present = {d for d in days if d in expected}
        missing = expected - present
        missing_months = sorted({m.replace(day=1) for m in missing})
        per_supply.append(
            SupplyCoverage(supply, len(present), len(expected), missing_months)
        )
    return Coverage(per_supply, [])


@dataclass
class AgileCoverage:
    daily_days: int
    hh_days: int
    missing_hh_days: list[date]
    daily_kwh: Decimal
    hh_kwh: Decimal
    divergence_pct: Decimal
    notes: list[str]

    @property
    def complete(self) -> bool:
        return not self.missing_hh_days and not self.notes


def agile_coverage(
    daily_days: set[date],
    hh_local_days: set[date],
    daily_kwh: Decimal,
    hh_kwh: Decimal,
    divergence_threshold: Decimal = Decimal("2"),
) -> AgileCoverage:
    """Coverage for the Agile compare: every day with daily data must have
    half-hourly data, and the two totals must agree within `divergence_threshold`%."""
    missing = sorted(daily_days - hh_local_days)
    if daily_kwh > 0:
        divergence = (abs(daily_kwh - hh_kwh) / daily_kwh * 100).quantize(Decimal("0.1"))
    else:
        divergence = Decimal(0)
    notes: list[str] = []
    if divergence > divergence_threshold:
        notes.append(
            f"half-hourly total ({hh_kwh} kWh) differs from daily total "
            f"({daily_kwh} kWh) by {divergence}%"
        )
    return AgileCoverage(
        daily_days=len(daily_days),
        hh_days=len(hh_local_days),
        missing_hh_days=missing,
        daily_kwh=daily_kwh,
        hh_kwh=hh_kwh,
        divergence_pct=divergence,
        notes=notes,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/bin/python -m pytest tests/test_coverage.py -v`
Expected: PASS (9 passed)

- [ ] **Step 5: Commit**

```bash
git add src/octopus_compare/coverage.py tests/test_coverage.py
git commit -m "feat: coverage detection for 3-way and agile comparisons"
```

---

### Task 3: Gas-unit confidence in `consumption.py`

**Files:**
- Modify: `src/octopus_compare/consumption.py`
- Test: `tests/test_consumption.py`

**Interfaces:**
- Produces:
  - `@dataclass GasUnitInfo` `{requested: str, resolved: str, confident: bool, factor: Decimal | None}` (`factor` = kWh per m³ when a conversion happens, else `None`).
  - `gas_unit_info(raw: dict[date, Decimal], gas_units: str, calorific_value: Decimal) -> GasUnitInfo`
  - `_resolve_gas_units(raw, gas_units) -> tuple[str, bool]` (now returns `(unit, confident)`).
- `to_kwh(raw, supply, gas_units, calorific_value) -> dict` keeps its external behaviour (returns the kWh dict) — it now reads only the unit from `_resolve_gas_units(...)[0]`.
- Module constants: `GAS_AMBIGUOUS_LOW = Decimal("4")`, `GAS_AMBIGUOUS_HIGH = Decimal("25")`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_consumption.py  (add these; keep existing tests)
from datetime import date
from decimal import Decimal

from octopus_compare.consumption import (
    _resolve_gas_units,
    gas_unit_info,
    GasUnitInfo,
)


def _raw(mean):
    # 10 days all equal to `mean`
    return {date(2026, 1, d): Decimal(str(mean)) for d in range(1, 11)}


def test_explicit_units_are_confident():
    assert _resolve_gas_units(_raw(8), "m3") == ("m3", True)
    assert _resolve_gas_units(_raw(8), "kwh") == ("kwh", True)


def test_auto_high_mean_is_confident_kwh():
    assert _resolve_gas_units(_raw(40), "auto") == ("kwh", True)


def test_auto_low_mean_is_confident_m3():
    assert _resolve_gas_units(_raw(2), "auto") == ("m3", True)


def test_auto_ambiguous_band_is_not_confident():
    unit, confident = _resolve_gas_units(_raw(8), "auto")
    assert confident is False  # 8 is in [4, 25)


def test_auto_empty_is_not_confident():
    assert _resolve_gas_units({}, "auto") == ("m3", False)


def test_gas_unit_info_reports_factor_for_m3():
    info = gas_unit_info(_raw(2), "auto", Decimal("39.5"))
    assert info == GasUnitInfo(
        requested="auto", resolved="m3", confident=True,
        factor=(Decimal("1.02264") * Decimal("39.5") / Decimal("3.6")),
    )


def test_gas_unit_info_no_factor_for_kwh():
    info = gas_unit_info(_raw(40), "auto", Decimal("39.5"))
    assert info.resolved == "kwh"
    assert info.factor is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_consumption.py -v`
Expected: FAIL — `ImportError: cannot import name 'gas_unit_info'` (and `_resolve_gas_units` returns a str, not a tuple).

- [ ] **Step 3: Write minimal implementation**

Replace the bottom of `consumption.py` (the `_resolve_gas_units` and `to_kwh` functions) and add the new pieces. Imports at top of file add `from dataclasses import dataclass` and `from octopus_compare.units import m3_to_kwh, VOLUME_CORRECTION`:

```python
# near the top imports
from dataclasses import dataclass
from octopus_compare.units import m3_to_kwh, VOLUME_CORRECTION

GAS_AMBIGUOUS_LOW = Decimal("4")
GAS_AMBIGUOUS_HIGH = Decimal("25")


@dataclass
class GasUnitInfo:
    requested: str
    resolved: str
    confident: bool
    factor: Decimal | None  # kWh per m3 when converting, else None


def _resolve_gas_units(raw: dict[date, Decimal], gas_units: str) -> tuple[str, bool]:
    if gas_units in ("m3", "kwh"):
        return gas_units, True
    if not raw:
        return "m3", False
    mean = sum(raw.values(), Decimal(0)) / len(raw)
    unit = "kwh" if mean > 15 else "m3"
    confident = not (GAS_AMBIGUOUS_LOW <= mean < GAS_AMBIGUOUS_HIGH)
    return unit, confident


def gas_unit_info(
    raw: dict[date, Decimal], gas_units: str, calorific_value: Decimal
) -> GasUnitInfo:
    resolved, confident = _resolve_gas_units(raw, gas_units)
    factor = (
        VOLUME_CORRECTION * Decimal(calorific_value) / Decimal("3.6")
        if resolved == "m3"
        else None
    )
    return GasUnitInfo(gas_units, resolved, confident, factor)


def to_kwh(raw, supply, gas_units, calorific_value):
    if supply == "electricity":
        return raw
    resolved, _ = _resolve_gas_units(raw, gas_units)
    if resolved == "kwh":
        return raw
    return {d: m3_to_kwh(v, calorific_value) for d, v in raw.items()}
```

Remove the now-duplicate `from octopus_compare.units import m3_to_kwh` line lower in the file if present (keep a single import at the top).

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/bin/python -m pytest tests/test_consumption.py -v`
Expected: PASS (existing + 7 new)

- [ ] **Step 5: Commit**

```bash
git add src/octopus_compare/consumption.py tests/test_consumption.py
git commit -m "feat: gas-unit auto-detection reports confidence + resolved unit"
```

---

### Task 4: `--allow-partial-data` config flag

**Files:**
- Modify: `src/octopus_compare/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `Config.allow_partial_data: bool` (default `False`), set from `--allow-partial-data` on both `compare` and `agile` subcommands.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py  (add)
from datetime import date

from octopus_compare.config import load_config

_ENV = {"OCTOPUS_API_KEY": "k", "OCTOPUS_ACCOUNT": "a"}


def test_allow_partial_data_defaults_false():
    cfg = load_config([], _ENV, date(2026, 6, 26))
    assert cfg.allow_partial_data is False


def test_allow_partial_data_flag_on_compare():
    cfg = load_config(["--allow-partial-data"], _ENV, date(2026, 6, 26))
    assert cfg.allow_partial_data is True


def test_allow_partial_data_flag_on_agile():
    cfg = load_config(["agile", "--allow-partial-data"], _ENV, date(2026, 6, 26))
    assert cfg.allow_partial_data is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_config.py -v`
Expected: FAIL — `AttributeError: 'Config' object has no attribute 'allow_partial_data'`

- [ ] **Step 3: Write minimal implementation**

In `config.py`: add the field to the dataclass (after `verbose`):

```python
    verbose: bool
    allow_partial_data: bool = False
```

Add the argument to the shared `common` parser (next to `--verbose`):

```python
    common.add_argument("--allow-partial-data", dest="allow_partial_data",
                        action="store_true")
```

Pass it through in the returned `Config(...)`:

```python
        verbose=args.verbose,
        allow_partial_data=args.allow_partial_data,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/bin/python -m pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/octopus_compare/config.py tests/test_config.py
git commit -m "feat: --allow-partial-data flag"
```

---

### Task 5: 3-way report rewrite (pipeline data + two-section presentation)

**Files:**
- Modify: `src/octopus_compare/report.py` (`MonthlyRow`, `ComparisonResult`, `recommend`, `format_text`, `format_json`, helpers)
- Modify: `src/octopus_compare/pipeline.py` (`run_comparison`, `_supply_breakdown` return)
- Modify: `src/octopus_compare/cli.py` (drop the verbose-only gas echo)
- Test: `tests/test_report.py`, `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `verdict.Verdict`, `verdict.decide`; `coverage.Coverage`, `coverage.compare_coverage`; `consumption.GasUnitInfo`, `consumption.gas_unit_info`.
- Produces (new `ComparisonResult` shape):
  - `MonthlyRow` `{month, days, flexible_pounds, tracker_pounds}` with property `verdict -> Verdict` (`decide(flexible, tracker)`).
  - `ComparisonResult` adds fields: `tracker_versions: list`, `coverage: Coverage`, `gas_units: GasUnitInfo | None`, `allow_partial: bool`. Keeps `elec_*`/`gas_*` for all three tariffs and totals. Drops the 3-way `cheapest` property.
  - `recommend(result) -> Verdict` returns the **backtest** verdict (Flexible vs Tracker).
  - `fixed_verdict(result) -> Verdict` returns `decide(flexible_total, fixed_total)`.
  - `verdict_suppressed(result) -> bool`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_report.py  (replace old recommend/format assertions with these;
# keep any still-valid ones)
from datetime import date
from decimal import Decimal

from octopus_compare.coverage import Coverage, SupplyCoverage
from octopus_compare.consumption import GasUnitInfo
from octopus_compare.costing import SupplyCost
from octopus_compare.report import (
    ComparisonResult, MonthlyRow, recommend, fixed_verdict,
    verdict_suppressed, format_text,
)
from octopus_compare.tracker import TrackerVersion, FixedProduct
from octopus_compare.verdict import Verdict


def _sc(total, energy="0", standing="0", vat="0", kwh="0"):
    return SupplyCost(
        consumption_kwh=Decimal(kwh), energy_pounds=Decimal(energy),
        standing_pounds=Decimal(standing), subtotal_pounds=Decimal("0"),
        vat_pounds=Decimal(vat), total_pounds=Decimal(total))


def _complete_coverage():
    return Coverage([SupplyCoverage("electricity", 90, 90, []),
                     SupplyCoverage("gas", 90, 90, [])], [])


def _result(flex_total, trk_total, fix_total, coverage=None, gas_units=None,
            allow_partial=False):
    tv = TrackerVersion("SILVER-26-01-01", "Tracker Jan", date(2026, 1, 1), None)
    fp = FixedProduct("OE-FIX-12M-26-06-24", "12M Fixed", date(2026, 6, 24))
    return ComparisonResult(
        period_from=date(2026, 1, 1), period_to=date(2026, 4, 1), region="C",
        tracker=tv, tracker_versions=[tv], fixed=fp,
        elec_flexible=_sc(flex_total), elec_tracker=_sc(trk_total),
        elec_fixed=_sc(fix_total),
        gas_flexible=_sc("0"), gas_tracker=_sc("0"), gas_fixed=_sc("0"),
        monthly=[], coverage=coverage or _complete_coverage(),
        gas_units=gas_units or GasUnitInfo("m3", "m3", True, Decimal("11.36")),
        allow_partial=allow_partial)


def test_recommend_is_flexible_vs_tracker_only():
    # Tracker far cheaper than Flexible, Fixed irrelevant to the backtest verdict
    assert recommend(_result("1000", "900", "500")) == Verdict.SWITCH
    assert recommend(_result("900", "1000", "500")) == Verdict.STAY
    assert recommend(_result("812", "820", "100")) == Verdict.TOO_CLOSE


def test_fixed_verdict_is_fixed_vs_flexible():
    assert fixed_verdict(_result("1000", "999", "900")) == Verdict.SWITCH


def test_verdict_suppressed_on_incomplete_coverage():
    cov = Coverage([SupplyCoverage("electricity", 90, 90, []),
                    SupplyCoverage("gas", 60, 90, [date(2026, 2, 1)])], [])
    assert verdict_suppressed(_result("1000", "900", "800", coverage=cov)) is True


def test_verdict_suppressed_on_ambiguous_gas():
    gi = GasUnitInfo("auto", "m3", False, Decimal("11.36"))
    assert verdict_suppressed(_result("1000", "900", "800", gas_units=gi)) is True


def test_allow_partial_unsuppresses():
    cov = Coverage([SupplyCoverage("electricity", 90, 90, []),
                    SupplyCoverage("gas", 60, 90, [date(2026, 2, 1)])], [])
    assert verdict_suppressed(
        _result("1000", "900", "800", coverage=cov, allow_partial=True)) is False


def test_format_text_has_two_sections_and_no_recommendation_banner():
    cov = Coverage([SupplyCoverage("electricity", 90, 90, []),
                    SupplyCoverage("gas", 60, 90, [date(2026, 2, 1)])], [])
    out = format_text(_result("1000", "900", "800", coverage=cov))
    assert "HISTORICAL BACKTEST" in out
    assert "FORWARD LOCK-IN CHECK" in out
    assert "NO RECOMMENDATION" in out
    assert "Coverage:" in out
    assert "Gas units:" in out


def test_format_text_shows_backtest_verdict_when_clean():
    out = format_text(_result("1000", "900", "1100"))
    assert "SWITCH" in out
    assert "NO RECOMMENDATION" not in out


def test_monthly_row_verdict_too_close_has_no_tick():
    out = format_text(ComparisonResultWithMonth())
    # the close month (£100.00 vs £100.40) must not be ticked
    assert "✓" not in out.split("By month")[1].split("Total")[0]


def ComparisonResultWithMonth():
    base = _result("100.40", "100.00", "200")
    base.monthly = [MonthlyRow(date(2026, 1, 1), 31,
                               Decimal("100.40"), Decimal("100.00"))]
    return base
```

> Note: delete the old `test_report.py` assertions that reference the removed
> 3-column `cheapest`, `_cheapest`, the old `recommend` returning strings
> ("STAY"/"SWITCH"/"MARGINAL"), and `MonthlyRow(... fixed_pounds=...)`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/bin/python -m pytest tests/test_report.py -v`
Expected: FAIL — `TypeError` on `ComparisonResult(... tracker_versions=...)` / `recommend` returning a `str`.

- [ ] **Step 3: Implement the report changes**

Replace the dataclasses, `recommend`, and the text/JSON formatters at the top of `report.py` (lines 14–213) with:

```python
from octopus_compare.verdict import Verdict, decide

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
    for row in result.monthly:
        v = row.verdict
        flex_win = v == Verdict.STAY
        trk_win = v == Verdict.SWITCH
        lines.append(
            f"  {_month_label(row.month, row.days):<20} "
            f"{_cell(row.flexible_pounds, flex_win):<14} "
            f"{_cell(row.tracker_pounds, trk_win)}"
        )
    tv = recommend(result)
    lines.append(
        f"  {'Total':<20} "
        f"{_cell(result.flexible_total, tv == Verdict.STAY):<14} "
        f"{_cell(result.tracker_total, tv == Verdict.SWITCH)}"
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
            "backtest": {"recommendation": recommend(result).value},
            "forward_lock_in": {
                "fixed_total": str(result.fixed_total),
                "delta_vs_flexible_pounds": str(result.flexible_total - result.fixed_total),
                "delta_pct": str(_pct(abs(result.flexible_total - result.fixed_total),
                                      result.flexible_total)),
                "verdict": fixed_verdict(result).value,
            },
            "verdict_suppressed": verdict_suppressed(result),
            "coverage": _coverage_json(result),
            "gas_units": (None if gi is None else
                          {"requested": gi.requested, "resolved": gi.resolved,
                           "confident": gi.confident,
                           "factor": (None if gi.factor is None else str(gi.factor))}),
        },
        indent=2,
    )
```

- [ ] **Step 4: Update `pipeline.py` to build the new result**

In `pipeline.py`, change `_supply_breakdown` to also return the version list and (for gas) the gas-unit info, then assemble the new `ComparisonResult`. Replace the imports and the two functions:

```python
from octopus_compare.consumption import fetch_daily, to_kwh, gas_unit_info
from octopus_compare.coverage import compare_coverage
```

Change the tail of `_supply_breakdown` to return `versions` and `gas_units` (None for electricity):

```python
def _supply_breakdown(client, supply, meter, cfg, fixed_product):
    flex = resolve_flexible(client, meter)
    region = cfg.region or region_letter(flex.tariff_code)

    raw = fetch_daily(client, supply, meter.identifier, meter.serials,
                      cfg.period_from, cfg.period_to)
    kwh = to_kwh(raw, supply, cfg.gas_units, cfg.gas_calorific_value)
    gas_units = (gas_unit_info(raw, cfg.gas_units, cfg.gas_calorific_value)
                 if supply == "gas" else None)

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
    return (region, latest, versions, gas_units,
            months["flexible"], months["tracker"], months["fixed"])
```

Replace `run_comparison`:

```python
def _priced_days(month_map) -> set:
    out = set()
    for days, _cost in month_map.values():
        out |= days
    return out


def run_comparison(client, config: Config) -> ComparisonResult:
    info = parse_account(client.get(f"accounts/{config.account}/"))
    fixed_product = resolve_fixed(client, config.fixed_product)

    (e_region, e_latest, e_versions, _e_gas,
     e_flex, e_trk, e_fix) = _supply_breakdown(
        client, "electricity", info.electricity, config, fixed_product)
    (_g_region, _g_latest, _g_versions, g_gas,
     g_flex, g_trk, g_fix) = _supply_breakdown(
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
            tracker_pounds=_month_total(e_trk, g_trk, month)))

    coverage = compare_coverage(
        config.period_from, config.period_to,
        {"electricity": _priced_days(e_flex), "gas": _priced_days(g_flex)})

    return ComparisonResult(
        period_from=config.period_from, period_to=config.period_to,
        region=e_region, tracker=e_latest, tracker_versions=e_versions,
        fixed=fixed_product,
        elec_flexible=agg(e_flex), elec_tracker=agg(e_trk), elec_fixed=agg(e_fix),
        gas_flexible=agg(g_flex), gas_tracker=agg(g_trk), gas_fixed=agg(g_fix),
        monthly=monthly, coverage=coverage, gas_units=g_gas,
        allow_partial=config.allow_partial_data,
    )
```

- [ ] **Step 5: Drop the verbose-only gas echo in `cli.py`**

Remove the `if cfg.verbose:` block (`cli.py:49-54`) — the resolved gas unit now always appears in the report. Leave the rest of `main` unchanged.

- [ ] **Step 6: Update `tests/test_pipeline.py`**

Find every construction/assertion that uses the removed `cheapest`, old `recommend` strings, 3-column `MonthlyRow`, or `_supply_breakdown`'s old 6-tuple return, and update them to the new shapes (the fake client in that file returns the same data — only the unpacking and assertions change). Assert `result.coverage.complete` and `result.gas_units.resolved` on the happy path.

- [ ] **Step 7: Run the full suite**

Run: `./.venv/bin/python -m pytest tests/test_report.py tests/test_pipeline.py -v`
Expected: PASS. Then `./.venv/bin/python -m pytest` — fix any other red tests that referenced the old report API (e.g. `test_smoke.py`, `test_cli.py`) by updating their expected strings to the two-section layout.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "feat: two-section 3-way report (same-basis backtest + forward fixed check)

Flexible vs Tracker is the only like-for-like head-to-head; Fixed is shown
separately as today's-rate-on-past-usage. Verdicts use the tie band and are
suppressed on incomplete/ambiguous data. Tracker relabelled to its historical
versions. Coverage + resolved gas unit always shown."
```

---

### Task 6: Agile decomposition reconciliation

**Files:**
- Modify: `src/octopus_compare/agile_breakdown.py` (`compute_decomposition`)
- Modify: `src/octopus_compare/report.py` (`_agile_decomposition_lines`)
- Test: `tests/test_agile_breakdown.py`, `tests/test_agile_report.py`

**Interfaces:**
- `compute_decomposition(...)` unchanged signature; now `behavioural_pounds = total_pounds - structural_pounds` (residual) so `structural_pounds + behavioural_pounds == total_pounds` exactly.
- `_agile_decomposition_lines(d, *, total_delta_pounds: Decimal, standing_delta_pounds: Decimal, vat_delta_pounds: Decimal)` — header verb driven by `total_delta_pounds`; adds a reconciliation line.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_agile_breakdown.py  (add)
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from octopus_compare.agile_breakdown import compute_decomposition

_UTC = ZoneInfo("UTC")


def test_pound_components_reconcile_exactly():
    rates = {datetime(2026, 1, 1, h, tzinfo=_UTC): Decimal("20") for h in range(5)}
    d = compute_decomposition(rates, Decimal("25.3"), Decimal("18.7"),
                              Decimal("1234.5"))
    assert d.structural_pounds + d.behavioural_pounds == d.total_pounds
```

```python
# tests/test_agile_report.py  (add)
from decimal import Decimal

from octopus_compare.agile_breakdown import Decomposition
from octopus_compare.report import _agile_decomposition_lines


def _decomp(total_p):
    return Decomposition(
        flex_p=Decimal("25"), time_avg_p=Decimal("22"), load_p=Decimal("20"),
        structural_p=Decimal("3"), behavioural_p=Decimal("2"), total_p=total_p,
        structural_pounds=Decimal("30"), behavioural_pounds=Decimal("20"),
        total_pounds=Decimal("50"), total_kwh=Decimal("1000"))


def test_header_follows_total_bill_not_energy():
    # energy favours Agile (total_p>0) but the bill total favours Flexible
    lines = _agile_decomposition_lines(
        _decomp(Decimal("5")), total_delta_pounds=Decimal("-2.50"),
        standing_delta_pounds=Decimal("-7.40"), vat_delta_pounds=Decimal("-0.25"))
    assert any("more expensive" in line for line in lines)
    assert any("Energy-only price pattern" in line for line in lines)
    assert any("=" in line and "Total" in line for line in lines)  # reconciliation
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/bin/python -m pytest tests/test_agile_breakdown.py tests/test_agile_report.py -v`
Expected: FAIL — reconciliation not exact / `_agile_decomposition_lines` signature mismatch.

- [ ] **Step 3: Make the decomposition residual exact**

In `agile_breakdown.py` `compute_decomposition`, replace the return's pounds lines:

```python
    total_pounds = pounds(total * total_kwh)
    structural_pounds = pounds(structural * total_kwh)
    behavioural_pounds = total_pounds - structural_pounds
    return Decomposition(
        flex_p=flex_effective_p, time_avg_p=time_avg, load_p=agile_effective_p,
        structural_p=structural, behavioural_p=behavioural, total_p=total,
        structural_pounds=structural_pounds,
        behavioural_pounds=behavioural_pounds,
        total_pounds=total_pounds,
        total_kwh=total_kwh,
    )
```

- [ ] **Step 4: Rewrite `_agile_decomposition_lines` in `report.py`**

```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `./.venv/bin/python -m pytest tests/test_agile_breakdown.py tests/test_agile_report.py -v`
Expected: PASS (the call site in `format_agile_text` is updated in Task 7; this task may leave `format_agile_text` temporarily calling the old signature — if the full suite is run now it will error there, so run only these two files until Task 7).

- [ ] **Step 6: Commit**

```bash
git add src/octopus_compare/agile_breakdown.py src/octopus_compare/report.py \
        tests/test_agile_breakdown.py tests/test_agile_report.py
git commit -m "feat: agile decomposition header follows total bill; £ parts reconcile"
```

---

### Task 7: Agile coverage + report wiring

**Files:**
- Modify: `src/octopus_compare/agile_pipeline.py` (`run_agile_comparison`)
- Modify: `src/octopus_compare/report.py` (`AgileResult`, `recommend_agile`, `_agile_block`, `_agile_reco_lines`, `format_agile_text`, `format_agile_json`)
- Test: `tests/test_agile_pipeline.py`, `tests/test_agile_report.py`

**Interfaces:**
- Consumes: `coverage.agile_coverage`, `coverage.AgileCoverage`; `verdict.decide`/`Verdict`.
- Produces: `AgileResult` adds `coverage: AgileCoverage`, `allow_partial: bool`. `recommend_agile(result) -> Verdict`. New `agile_verdict_suppressed(result) -> bool`. `_agile_block` shows Flexible consumption too.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_agile_report.py  (add)
from datetime import date
from decimal import Decimal

from octopus_compare.coverage import AgileCoverage
from octopus_compare.costing import SupplyCost
from octopus_compare.report import (
    AgileResult, agile_verdict_suppressed, format_agile_text, recommend_agile,
)
from octopus_compare.verdict import Verdict


def _sc(total, kwh="100"):
    return SupplyCost(Decimal(kwh), Decimal("0"), Decimal("0"), Decimal("0"),
                      Decimal("0"), Decimal(total))


def _agile_cov(complete=True):
    if complete:
        return AgileCoverage(30, 30, [], Decimal("100"), Decimal("100"),
                             Decimal("0"), [])
    return AgileCoverage(30, 15, [date(2026, 1, 5)], Decimal("100"),
                         Decimal("50"), Decimal("50.0"),
                         ["half-hourly total (50 kWh) differs from daily total (100 kWh) by 50.0%"])


def _agile_result(flex, agile, cov):
    # minimal stub: insight/breakdown not exercised by these tests
    return AgileResult(
        period_from=date(2026, 1, 1), period_to=date(2026, 2, 1), region="C",
        agile_versions=[], elec_flexible=_sc(flex), elec_agile=_sc(agile),
        monthly=[], insight=None, breakdown=None, coverage=cov,
        allow_partial=False)


def test_agile_verdict_suppressed_on_partial():
    assert agile_verdict_suppressed(_agile_result("100", "90", _agile_cov(False))) is True


def test_agile_recommend_uses_tie_band():
    assert recommend_agile(_agile_result("1000", "900", _agile_cov())) == Verdict.SWITCH
    assert recommend_agile(_agile_result("812", "820", _agile_cov())) == Verdict.STAY
```

```python
# tests/test_agile_pipeline.py  (add to the existing happy-path test's assertions)
#   assert result.coverage.complete
#   assert result.elec_flexible.consumption_kwh == result.elec_agile.consumption_kwh
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/bin/python -m pytest tests/test_agile_report.py -v`
Expected: FAIL — `AgileResult` has no `coverage`/`allow_partial`; `agile_verdict_suppressed` undefined; `recommend_agile` returns a str.

- [ ] **Step 3: Update `AgileResult` + recommend + block + reco in `report.py`**

```python
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
```

Update `format_agile_text` to: call the new `_agile_decomposition_lines` with the bill deltas, and append coverage lines before the disclaimer:

```python
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
    for row in result.monthly:
        c = row.cheapest
        lines.append(
            f"  {_month_label(row.month, row.days):<20} "
            f"{_cell(row.flexible_pounds, c == 'flexible'):<14}"
            f"{_cell(row.agile_pounds, c == 'agile')}"
        )
    lines.append(
        f"  {'Total':<20} "
        f"{_cell(result.flexible_total, recommend_agile(result) == Verdict.STAY):<14}"
        f"{_cell(result.agile_total, recommend_agile(result) == Verdict.SWITCH)}"
    )
    lines.append("")
    lines += _agile_insight_lines(result.insight)
    f, a = result.elec_flexible, result.elec_agile
    lines += _agile_decomposition_lines(
        result.breakdown.decomposition,
        total_delta_pounds=f.total_pounds - a.total_pounds,
        standing_delta_pounds=f.standing_pounds - a.standing_pounds,
        vat_delta_pounds=f.vat_pounds - a.vat_pounds)
    lines += _agile_hour_lines(result.breakdown)
    lines += _agile_reco_lines(result)
    lines.append("")
    lines += _agile_coverage_lines(result)
    lines.append("Figures are API-derived estimates incl. VAT, not your exact bill.")
    return "\n".join(lines)
```

In `format_agile_json`, add `"recommendation": recommend_agile(result).value`, `"verdict_suppressed": agile_verdict_suppressed(result)`, and a `"coverage"` block (`daily_days`, `hh_days`, `missing_hh_days` as ISO strings, `daily_kwh`, `hh_kwh`, `divergence_pct`, `notes`). Keep `AgileMonthlyRow.cheapest` as-is (it is a per-month arithmetic mark; the authoritative verdict is the total).

- [ ] **Step 4: Wire coverage into `agile_pipeline.py`**

Add imports and compute coverage from the half-hourly vs daily data:

```python
from octopus_compare.coverage import agile_coverage
```

Before building `AgileResult`, compute:

```python
    daily_days = set(daily)
    hh_local_days = {i.astimezone(_LONDON).date() for i in hh}
    daily_kwh = sum((Decimal(v) for v in daily.values()), Decimal(0))
    coverage = agile_coverage(daily_days, hh_local_days, daily_kwh,
                              elec_agile.consumption_kwh)
```

and pass `coverage=coverage, allow_partial=config.allow_partial_data` into `AgileResult(...)`.

- [ ] **Step 5: Run the full suite**

Run: `./.venv/bin/python -m pytest`
Expected: PASS. Fix any remaining agile report/pipeline tests that assert the old strings (`Why Agile is cheaper` placement, missing coverage line, etc.).

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: agile coverage detection + verdict suppression + show flex consumption"
```

---

### Task 8: Full verification & docs

**Files:**
- Modify: `README.md` (note the two-section output, `--allow-partial-data`, that Fixed is today's-rate-on-past-usage)
- Test: whole suite

- [ ] **Step 1: Run the entire suite**

Run: `./.venv/bin/python -m pytest`
Expected: PASS (all green; the 3 live-eval tests still skipped without `OCTOPUS_LIVE_EVAL`).

- [ ] **Step 2: Smoke-check the rendered text offline**

Construct a `ComparisonResult` (reuse the `test_report.py` helpers) and `print(format_text(...))` in a throwaway `./.venv/bin/python -c` snippet; eyeball that both sections, the coverage line, the gas-units line, and the disclaimer render and align. Do the same for `format_agile_text`.

- [ ] **Step 3: Update README**

In `README.md`, under Usage/output: state that the 3-way report now shows a **historical backtest (Flexible vs Tracker)** and a separate **forward 12M-Fixed lock-in check**, that a winner is only declared when it clears the >2%/>£5 band, that incomplete/ambiguous data suppresses the recommendation unless `--allow-partial-data` is passed, and that the resolved gas unit is always shown. Document the `--allow-partial-data` flag.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: README for two-section report, tie band, and --allow-partial-data"
```

---

## Self-review notes (completed by plan author)

- **Spec coverage:** finding #1 → Tasks 5 (separation) ; #2 → Task 5 (relabel + versions_used) ; #3 → Tasks 2,7 (agile coverage + show flex kWh) ; #4 → Tasks 3,5 (confidence + always-shown unit + suppression) ; #5 → Tasks 1,5,7 (tie band on totals) ; #6 → Task 6 (header follows total + reconciliation) ; #7 → Tasks 2,5 (coverage + suppression) ; #8 → Tasks 1,5 (band on monthly ✓ and total).
- **Types consistent:** `Verdict` used identically across report/agile; `decide()` signature stable; `GasUnitInfo`/`Coverage`/`AgileCoverage` field names match between producer (coverage.py/consumption.py) and consumers (report.py/pipeline.py/agile_pipeline.py).
- **No placeholders:** every code step contains full function bodies.
```
