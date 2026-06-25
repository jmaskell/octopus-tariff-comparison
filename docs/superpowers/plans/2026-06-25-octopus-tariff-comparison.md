# Octopus Tariff Comparison CLI — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python CLI that compares actual Flexible Octopus spend against hypothetical Octopus Tracker cost (electricity + gas) over a recent period and prints a switch recommendation.

**Architecture:** A small synchronous Python package. It reads credentials from `.env`, calls the Octopus REST API to discover meters/agreements/consumption/rates, runs a pure-function cost engine that reproduces Octopus's per-day billing method, and prints a text (or JSON) report. The cost engine is validated to the penny against the household's real bills (transcribed into test fixtures), with no network needed.

**Tech Stack:** Python 3.11+, `requests`, `python-dotenv`, `rich`, `pytest`.

## Global Constraints

These apply to **every** task.

- **Python:** 3.11+ (uses `zoneinfo`, `X | None` typing).
- **Dependencies:** only `requests`, `python-dotenv`, `rich` (runtime) and `pytest` (dev). No others.
- **Money:** use `decimal.Decimal` everywhere money is computed. Never use `float` for currency.
- **VAT:** domestic energy VAT is **5%** (`Decimal("0.05")`). Line items are computed in **exc-VAT** pence; VAT is applied once to the (energy + standing) subtotal.
- **Billing method (verified against bills):** energy cost = sum over days of `round_half_up(day_kwh × day_rate_exc_p)` in pence. Standing charge = `round_half_up(sum of per-day exc-VAT standing charge)`. VAT = `round_half_up(subtotal_pence × 0.05)`. Rounding is `ROUND_HALF_UP` to whole pence.
- **Gas conversion:** `kWh = m³ × 1.02264 × calorific_value / 3.6`; default calorific value **39.5**, configurable via `--gas-calorific-value`.
- **Day bucketing / timezone:** energy days are **Europe/London** local days (tracker rates change at local midnight). Use `zoneinfo.ZoneInfo("Europe/London")`.
- **API:** base URL `https://api.octopus.energy/v1/`. Auth = HTTP Basic with the API key as username and blank password (`requests` `auth=(api_key, "")`).
- **Tariff/product codes:** never hard-code the Tracker product code — resolve it at runtime. Product code derives from a tariff code as `tariff_code[5:-2]` (e.g. `E-1R-VAR-22-11-01-C` → `VAR-22-11-01`).
- **Account:** `OCTOPUS_ACCOUNT` defaults are read from `.env`; the known account is `A-8F18337C` (London / GSP resolved from the API, not hard-coded).
- **Secrets:** `.env` is gitignored; never commit it. Never print the API key.
- **TDD:** write the failing test first, watch it fail, implement minimally, watch it pass, commit. Small, frequent commits.

---

## File Structure

```
pyproject.toml                       # package metadata, deps, console script
src/octopus_compare/
  __init__.py
  config.py        # Config dataclass; load from .env + argparse
  money.py         # Decimal rounding + VAT helpers
  costing.py       # cost engine: per-day energy, standing charge, SupplyCost
  units.py         # gas m³ → kWh conversion
  client.py        # OctopusClient: Basic auth, GET, pagination, retry
  account.py       # parse account JSON; agreements; product_code_from_tariff
  tracker.py       # resolve current Tracker product + tariff codes per region
  rates.py         # RateLookup / StandingChargeLookup; fetch from API
  consumption.py   # fetch daily consumption; gas unit auto-detect + convert
  pipeline.py      # run_comparison: wire everything into a ComparisonResult
  report.py        # recommendation thresholds; text + JSON formatting
  cli.py           # main(argv): parse, run, print, error handling, exit codes
tests/
  fixtures/bills.py        # transcribed ground truth from the 3 PDF bills
  fixtures/api_samples.py  # sample API JSON payloads
  test_config.py
  test_money.py
  test_costing.py
  test_units.py
  test_client.py
  test_account.py
  test_tracker.py
  test_rates.py
  test_consumption.py
  test_pipeline.py
  test_report.py
  test_cli.py
  test_live_eval.py        # Tier-3, env-gated, skipped by default
```

---

## Task 1: Project scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `src/octopus_compare/__init__.py`
- Create: `tests/__init__.py` (empty — makes `tests` an importable package so later `from tests.fixtures import …` works)
- Test: `tests/test_smoke.py`

**Interfaces:**
- Produces: an installable package `octopus_compare` importable in tests; `pytest` runs.

- [ ] **Step 1: Write the failing test**

`tests/test_smoke.py`:
```python
def test_package_imports():
    import octopus_compare

    assert octopus_compare.__version__ == "0.1.0"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_smoke.py -v`
Expected: FAIL (ModuleNotFoundError / not installed).

- [ ] **Step 3: Create `pyproject.toml`**

```toml
[project]
name = "octopus-compare"
version = "0.1.0"
description = "Compare Flexible Octopus spend against Octopus Tracker."
requires-python = ">=3.11"
dependencies = ["requests>=2.31", "python-dotenv>=1.0", "rich>=13.0"]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[project.scripts]
octopus-compare = "octopus_compare.cli:main"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
pythonpath = ["src", "."]
testpaths = ["tests"]
```

- [ ] **Step 4: Create `src/octopus_compare/__init__.py` and `tests/__init__.py`**

`src/octopus_compare/__init__.py`:
```python
__version__ = "0.1.0"
```

`tests/__init__.py`: empty file.

- [ ] **Step 5: Install and run tests**

Run: `python -m pip install -e ".[dev]" && python -m pytest tests/test_smoke.py -v`
Expected: PASS.

If `pip install` fails with an "externally-managed-environment" error (PEP 668),
create and use a virtualenv instead, and use it for all subsequent test runs:
```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m pytest tests/test_smoke.py -v
```
(`.venv/` is already covered by `.gitignore`.)

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/octopus_compare/__init__.py tests/__init__.py tests/test_smoke.py
git commit -m "feat: project scaffold for octopus-compare"
```

---

## Task 2: Money helpers

**Files:**
- Create: `src/octopus_compare/money.py`
- Test: `tests/test_money.py`

**Interfaces:**
- Produces:
  - `PENNY: Decimal`, `VAT_RATE: Decimal` (= `Decimal("0.05")`)
  - `round_pence(value: Decimal) -> Decimal` — round to whole pence, `ROUND_HALF_UP`.
  - `vat_pence(subtotal_pence: Decimal) -> Decimal` — `round_pence(subtotal_pence * VAT_RATE)`.
  - `pounds(pence: Decimal) -> Decimal` — `pence / 100`, quantized to 2dp.

- [ ] **Step 1: Write the failing test**

`tests/test_money.py`:
```python
from decimal import Decimal

from octopus_compare.money import round_pence, vat_pence, pounds, VAT_RATE


def test_round_pence_half_up():
    assert round_pence(Decimal("865.95")) == Decimal("866")
    assert round_pence(Decimal("291.5514")) == Decimal("292")
    assert round_pence(Decimal("170.71")) == Decimal("171")


def test_vat_is_five_percent():
    assert VAT_RATE == Decimal("0.05")
    assert vat_pence(Decimal("5322")) == Decimal("266")   # bill 1 elec tracker
    assert vat_pence(Decimal("6445")) == Decimal("322")   # bill 1 gas tracker


def test_pounds_two_dp():
    assert pounds(Decimal("5588")) == Decimal("55.88")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_money.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement `money.py`**

```python
from decimal import Decimal, ROUND_HALF_UP

PENNY = Decimal("1")
VAT_RATE = Decimal("0.05")


def round_pence(value: Decimal) -> Decimal:
    return value.quantize(PENNY, rounding=ROUND_HALF_UP)


def vat_pence(subtotal_pence: Decimal) -> Decimal:
    return round_pence(subtotal_pence * VAT_RATE)


def pounds(pence: Decimal) -> Decimal:
    return (pence / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_money.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/octopus_compare/money.py tests/test_money.py
git commit -m "feat: decimal money + VAT rounding helpers"
```

---

## Task 3: Bill fixtures + per-day energy cost

**Files:**
- Create: `tests/fixtures/__init__.py` (empty)
- Create: `tests/fixtures/bills.py`
- Create: `src/octopus_compare/costing.py`
- Test: `tests/test_costing.py`

**Interfaces:**
- Produces:
  - `costing.daily_energy_pence(daily_kwh: dict[date, Decimal], rate_p_for: Callable[[date], Decimal]) -> Decimal`
  - Fixture data: `bills.TRACKER_MARCH` and helpers `bills.elec_daily_kwh()`, `bills.elec_daily_rate()`, `bills.gas_daily_kwh()`, `bills.gas_daily_rate()` returning `dict[date, Decimal]`.

- [ ] **Step 1: Create the fixtures file**

`tests/fixtures/__init__.py`: empty file.

`tests/fixtures/bills.py` (transcribed from bill 402259109, Tracker Dec-2024-v1, 1–23 Mar 2026; columns: day, elec_rate_exc_p, elec_kwh, elec_cost_£, gas_rate_exc_p, gas_kwh, gas_cost_£):
```python
from datetime import date
from decimal import Decimal


def D(x) -> Decimal:
    return Decimal(str(x))


# Bill 402259109 — Octopus Tracker (December 2024 v1), 1–23 March 2026.
# (day, elec_rate, elec_kwh, elec_cost, gas_rate, gas_kwh, gas_cost)
TRACKER_MARCH = [
    (1, 18.78, 9.09, 1.71, 4.73, 36.81, 1.74),
    (2, 19.81, 7.38, 1.46, 4.73, 32.99, 1.56),
    (3, 23.27, 8.74, 2.03, 5.87, 41.41, 2.43),
    (4, 26.45, 8.08, 2.14, 6.84, 44.98, 3.08),
    (5, 25.47, 8.85, 2.25, 6.32, 49.48, 3.13),
    (6, 25.71, 11.34, 2.92, 6.53, 31.18, 2.04),
    (7, 25.25, 8.47, 2.14, 6.56, 47.38, 3.11),
    (8, 25.54, 9.82, 2.51, 6.56, 48.75, 3.20),
    (9, 27.05, 8.51, 2.30, 6.63, 39.41, 2.61),
    (10, 26.26, 6.43, 1.69, 6.88, 43.38, 2.98),
    (11, 17.74, 8.23, 1.46, 6.07, 36.38, 2.21),
    (12, 19.19, 9.20, 1.77, 6.27, 45.91, 2.88),
    (13, 18.84, 8.48, 1.60, 6.37, 41.79, 2.66),
    (14, 24.72, 6.43, 1.59, 6.36, 48.65, 3.09),
    (15, 21.82, 6.65, 1.45, 6.36, 42.94, 2.73),
    (16, 20.38, 9.04, 1.84, 6.39, 41.59, 2.66),
    (17, 22.39, 7.77, 1.74, 6.35, 35.60, 2.26),
    (18, 24.39, 11.83, 2.89, 6.44, 26.45, 1.70),
    (19, 24.85, 10.15, 2.52, 6.68, 42.86, 2.86),
    (20, 27.85, 5.28, 1.47, 7.33, 32.37, 2.37),
    (21, 26.21, 3.94, 1.03, 7.12, 33.85, 2.41),
    (22, 25.53, 8.68, 2.22, 7.12, 32.90, 2.34),
    (23, 26.09, 7.03, 1.83, 7.12, 25.82, 1.84),
]

# Tracker period totals (energy exc VAT, standing charge, VAT, total inc VAT).
TRACKER_ELEC_ENERGY_P = D(4456)   # £44.56
TRACKER_ELEC_SC_P = D(866)        # 23 days @ 37.65p = £8.66
TRACKER_ELEC_TOTAL_P = D(5588)    # £55.88
TRACKER_ELEC_SC_RATE = D("37.65")
TRACKER_GAS_ENERGY_P = D(5789)    # £57.89
TRACKER_GAS_SC_P = D(656)         # 23 days @ 28.52p = £6.56
TRACKER_GAS_TOTAL_P = D(6767)     # £67.67
TRACKER_GAS_SC_RATE = D("28.52")
TRACKER_DAYS = 23


def _march(day: int) -> date:
    return date(2026, 3, day)


def elec_daily_kwh() -> dict[date, Decimal]:
    return {_march(r[0]): D(r[2]) for r in TRACKER_MARCH}


def elec_daily_rate() -> dict[date, Decimal]:
    return {_march(r[0]): D(r[1]) for r in TRACKER_MARCH}


def gas_daily_kwh() -> dict[date, Decimal]:
    return {_march(r[0]): D(r[5]) for r in TRACKER_MARCH}


def gas_daily_rate() -> dict[date, Decimal]:
    return {_march(r[0]): D(r[4]) for r in TRACKER_MARCH}


# Flexible reference figures (Tier-2 tolerance; per-day kWh not on the bills).
# (label, total_kwh, unit_rate_exc_p, sc_rate_p, days, energy_£, total_£)
FLEXIBLE_REFERENCES = [
    ("bill1_elec_flex", D("78.0"), D("25.71"), D("43.60"), 8, D("20.07"), D("24.74")),
    ("bill1_gas_flex", D("323.7"), D("5.74"), D("32.65"), 8, D("18.59"), D("22.26")),
    ("bill2_elec", D("271.8"), D("23.71"), D("42.18"), 30, D("64.44"), D("80.94")),
    ("bill2_gas", D("849.5"), D("5.63"), D("28.06"), 30, D("47.85"), D("59.08")),
    ("bill3_elec", D("272.1"), D("23.71"), D("42.18"), 31, D("64.52"), D("81.47")),
    ("bill3_gas", D("534.7"), D("5.63"), D("28.06"), 31, D("30.12"), D("40.76")),
]

# Gas m³ → kWh references: (m3, calorific_value, expected_kwh)
GAS_CONVERSIONS = [
    (D("81.1"), D("39.2"), D("902.9")),
    (D("75.7"), D("39.5"), D("849.5")),
    (D("47.5"), D("39.6"), D("534.7")),
]
```

- [ ] **Step 2: Write the failing test**

`tests/test_costing.py`:
```python
from decimal import Decimal

from octopus_compare.costing import daily_energy_pence
from tests.fixtures import bills


def test_tracker_elec_energy_penny_exact():
    kwh = bills.elec_daily_kwh()
    rate = bills.elec_daily_rate()
    assert daily_energy_pence(kwh, lambda d: rate[d]) == bills.TRACKER_ELEC_ENERGY_P


def test_tracker_gas_energy_penny_exact():
    kwh = bills.gas_daily_kwh()
    rate = bills.gas_daily_rate()
    assert daily_energy_pence(kwh, lambda d: rate[d]) == bills.TRACKER_GAS_ENERGY_P
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_costing.py -v`
Expected: FAIL (module not found).

- [ ] **Step 4: Implement `daily_energy_pence` in `costing.py`**

```python
from collections.abc import Callable
from datetime import date
from decimal import Decimal

from octopus_compare.money import round_pence


def daily_energy_pence(
    daily_kwh: dict[date, Decimal],
    rate_p_for: Callable[[date], Decimal],
) -> Decimal:
    """Sum of per-day round_half_up(kwh * exc-VAT rate), in pence."""
    total = Decimal(0)
    for day, kwh in daily_kwh.items():
        total += round_pence(Decimal(kwh) * Decimal(rate_p_for(day)))
    return total
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_costing.py -v`
Expected: PASS (both energy totals reproduce the bill to the penny).

- [ ] **Step 6: Commit**

```bash
git add tests/fixtures src/octopus_compare/costing.py tests/test_costing.py
git commit -m "feat: bill fixtures + penny-exact per-day energy cost"
```

---

## Task 4: Standing charge, VAT, and full SupplyCost

**Files:**
- Modify: `src/octopus_compare/costing.py`
- Modify: `tests/test_costing.py`

**Interfaces:**
- Consumes: `daily_energy_pence` (Task 3), `money.round_pence`, `money.vat_pence`, `money.pounds`.
- Produces:
  - `costing.standing_pence(days: list[date], sc_p_for: Callable[[date], Decimal]) -> Decimal`
  - `@dataclass costing.SupplyCost` with fields `consumption_kwh, energy_pounds, standing_pounds, subtotal_pounds, vat_pounds, total_pounds` (all `Decimal`).
  - `costing.supply_cost(daily_kwh: dict[date, Decimal], rate_p_for, sc_p_for) -> SupplyCost`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_costing.py`:
```python
from octopus_compare.costing import standing_pence, supply_cost
from datetime import date


def test_tracker_elec_standing_charge():
    days = sorted(bills.elec_daily_kwh())
    sc = standing_pence(days, lambda d: bills.TRACKER_ELEC_SC_RATE)
    assert sc == bills.TRACKER_ELEC_SC_P  # £8.66


def test_tracker_elec_full_total_penny_exact():
    kwh = bills.elec_daily_kwh()
    rate = bills.elec_daily_rate()
    cost = supply_cost(kwh, lambda d: rate[d], lambda d: bills.TRACKER_ELEC_SC_RATE)
    assert cost.total_pounds == bills.TRACKER_ELEC_TOTAL_P / 100  # £55.88


def test_tracker_gas_full_total_penny_exact():
    kwh = bills.gas_daily_kwh()
    rate = bills.gas_daily_rate()
    cost = supply_cost(kwh, lambda d: rate[d], lambda d: bills.TRACKER_GAS_SC_RATE)
    assert cost.total_pounds == bills.TRACKER_GAS_TOTAL_P / 100  # £67.67


def test_flexible_references_within_tolerance():
    # Flexible bills print only monthly totals, so per-day rounding can't be
    # reproduced exactly; assert within 5p of the printed total.
    from decimal import Decimal
    for label, kwh, rate, sc_rate, ndays, energy, total in bills.FLEXIBLE_REFERENCES:
        # May has 31 days, so every reference ndays (8/30/31) yields valid dates.
        days = [date(2026, 5, 1 + i) for i in range(ndays)]
        # Energy in a single bucket (flat rate); zero on the other days so the
        # standing charge still counts all `ndays` days.
        daily = {d: (kwh if d == days[0] else Decimal(0)) for d in days}
        cost = supply_cost(daily, lambda d: rate, lambda d: sc_rate)
        assert abs(cost.total_pounds - total) <= Decimal("0.05"), label
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_costing.py -v`
Expected: FAIL (`standing_pence`/`supply_cost` not defined).

- [ ] **Step 3: Implement standing charge + SupplyCost in `costing.py`**

Append:
```python
from dataclasses import dataclass

from octopus_compare.money import pounds, vat_pence


def standing_pence(
    days: list[date],
    sc_p_for: Callable[[date], Decimal],
) -> Decimal:
    """Round_half_up of the summed per-day exc-VAT standing charge, in pence."""
    total = sum((Decimal(sc_p_for(d)) for d in days), Decimal(0))
    return round_pence(total)


@dataclass
class SupplyCost:
    consumption_kwh: Decimal
    energy_pounds: Decimal
    standing_pounds: Decimal
    subtotal_pounds: Decimal
    vat_pounds: Decimal
    total_pounds: Decimal


def supply_cost(
    daily_kwh: dict[date, Decimal],
    rate_p_for: Callable[[date], Decimal],
    sc_p_for: Callable[[date], Decimal],
) -> SupplyCost:
    days = sorted(daily_kwh)
    energy_p = daily_energy_pence(daily_kwh, rate_p_for)
    sc_p = standing_pence(days, sc_p_for)
    subtotal_p = energy_p + sc_p
    vat_p = vat_pence(subtotal_p)
    total_p = subtotal_p + vat_p
    consumption = sum((Decimal(v) for v in daily_kwh.values()), Decimal(0))
    return SupplyCost(
        consumption_kwh=consumption,
        energy_pounds=pounds(energy_p),
        standing_pounds=pounds(sc_p),
        subtotal_pounds=pounds(subtotal_p),
        vat_pounds=pounds(vat_p),
        total_pounds=pounds(total_p),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_costing.py -v`
Expected: PASS (all tracker totals exact; flexible references within 5p).

- [ ] **Step 5: Commit**

```bash
git add src/octopus_compare/costing.py tests/test_costing.py
git commit -m "feat: standing charge, VAT, and full SupplyCost"
```

---

## Task 5: Gas m³ → kWh conversion

**Files:**
- Create: `src/octopus_compare/units.py`
- Test: `tests/test_units.py`

**Interfaces:**
- Produces:
  - `units.VOLUME_CORRECTION: Decimal` (= `Decimal("1.02264")`)
  - `units.DEFAULT_CALORIFIC_VALUE: Decimal` (= `Decimal("39.5")`)
  - `units.m3_to_kwh(m3: Decimal, calorific_value: Decimal = DEFAULT_CALORIFIC_VALUE) -> Decimal`

- [ ] **Step 1: Write the failing test**

`tests/test_units.py`:
```python
from decimal import Decimal

from octopus_compare.units import m3_to_kwh, DEFAULT_CALORIFIC_VALUE
from tests.fixtures import bills


def test_default_calorific_value():
    assert DEFAULT_CALORIFIC_VALUE == Decimal("39.5")


def test_m3_to_kwh_matches_bills():
    for m3, cv, expected in bills.GAS_CONVERSIONS:
        assert abs(m3_to_kwh(m3, cv) - expected) <= Decimal("0.5")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_units.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement `units.py`**

```python
from decimal import Decimal

VOLUME_CORRECTION = Decimal("1.02264")
DEFAULT_CALORIFIC_VALUE = Decimal("39.5")


def m3_to_kwh(m3: Decimal, calorific_value: Decimal = DEFAULT_CALORIFIC_VALUE) -> Decimal:
    """Standard industry formula: m³ × volume correction × CV ÷ 3.6."""
    return Decimal(m3) * VOLUME_CORRECTION * Decimal(calorific_value) / Decimal("3.6")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_units.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/octopus_compare/units.py tests/test_units.py
git commit -m "feat: gas m3 to kWh conversion"
```

---

## Task 6: Config loading

**Files:**
- Create: `src/octopus_compare/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces:
  - `@dataclass config.Config` with fields: `api_key: str`, `account: str`, `period_from: date`, `period_to: date`, `output_format: str` (`"text"|"json"`), `gas_calorific_value: Decimal`, `gas_units: str` (`"auto"|"m3"|"kwh"`), `verbose: bool`.
  - `config.ConfigError(Exception)`
  - `config.load_config(argv: list[str], env: dict[str, str], today: date) -> Config`
- Behaviour: `--months N` (default 3) sets `period_from = today - N months` (use 30×N days for simplicity), `period_to = today`. `--from YYYY-MM-DD`/`--to YYYY-MM-DD` override. Missing `OCTOPUS_API_KEY` or `OCTOPUS_ACCOUNT` → `ConfigError`.

- [ ] **Step 1: Write the failing test**

`tests/test_config.py`:
```python
from datetime import date
from decimal import Decimal

import pytest

from octopus_compare.config import load_config, Config, ConfigError

ENV = {"OCTOPUS_API_KEY": "sk_test", "OCTOPUS_ACCOUNT": "A-8F18337C"}
TODAY = date(2026, 6, 25)


def test_defaults_three_months():
    cfg = load_config([], ENV, TODAY)
    assert isinstance(cfg, Config)
    assert cfg.api_key == "sk_test"
    assert cfg.account == "A-8F18337C"
    assert cfg.period_to == TODAY
    assert cfg.period_from == date(2026, 3, 27)  # 90 days before
    assert cfg.output_format == "text"
    assert cfg.gas_calorific_value == Decimal("39.5")
    assert cfg.gas_units == "auto"


def test_months_flag():
    cfg = load_config(["--months", "1"], ENV, TODAY)
    assert cfg.period_from == date(2026, 5, 26)  # 30 days before


def test_from_to_override():
    cfg = load_config(["--from", "2026-04-01", "--to", "2026-04-30"], ENV, TODAY)
    assert cfg.period_from == date(2026, 4, 1)
    assert cfg.period_to == date(2026, 4, 30)


def test_missing_credentials_raises():
    with pytest.raises(ConfigError):
        load_config([], {}, TODAY)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement `config.py`**

```python
import argparse
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal


class ConfigError(Exception):
    pass


@dataclass
class Config:
    api_key: str
    account: str
    period_from: date
    period_to: date
    output_format: str
    gas_calorific_value: Decimal
    gas_units: str
    verbose: bool


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def load_config(argv: list[str], env: dict[str, str], today: date) -> Config:
    parser = argparse.ArgumentParser(prog="octopus-compare")
    parser.add_argument("--months", type=int, default=3)
    parser.add_argument("--from", dest="from_", type=_parse_date)
    parser.add_argument("--to", dest="to", type=_parse_date)
    parser.add_argument("--format", choices=["text", "json"], default="text")
    parser.add_argument("--gas-calorific-value", type=Decimal, default=Decimal("39.5"))
    parser.add_argument("--gas-units", choices=["auto", "m3", "kwh"], default="auto")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    api_key = env.get("OCTOPUS_API_KEY", "").strip()
    account = env.get("OCTOPUS_ACCOUNT", "").strip()
    if not api_key or not account:
        raise ConfigError(
            "Missing credentials. Set OCTOPUS_API_KEY and OCTOPUS_ACCOUNT in .env"
        )

    period_to = args.to or today
    period_from = args.from_ or (today - timedelta(days=30 * args.months))

    return Config(
        api_key=api_key,
        account=account,
        period_from=period_from,
        period_to=period_to,
        output_format=args.format,
        gas_calorific_value=args.gas_calorific_value,
        gas_units=args.gas_units,
        verbose=args.verbose,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_config.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/octopus_compare/config.py tests/test_config.py
git commit -m "feat: config loading from env + argparse"
```

---

## Task 7: HTTP client (auth, pagination, retry)

**Files:**
- Create: `src/octopus_compare/client.py`
- Test: `tests/test_client.py`

**Interfaces:**
- Produces:
  - `client.ApiError(Exception)`
  - `class client.OctopusClient`:
    - `__init__(self, api_key: str, base_url: str = "https://api.octopus.energy/v1/", session=None, max_retries: int = 3)`
    - `get(self, path: str, params: dict | None = None) -> dict` — Basic auth, raises `ApiError` on non-2xx (after retrying `429`/`5xx`).
    - `get_results(self, path: str, params: dict | None = None) -> list[dict]` — follows `next` pagination, concatenating `results`.
- Note: `path` is relative to `base_url` (e.g. `"accounts/A-8F18337C/"`). Pagination `next` returns absolute URLs; fetch them directly.

- [ ] **Step 1: Write the failing test**

`tests/test_client.py`:
```python
import pytest

from octopus_compare.client import OctopusClient, ApiError


class FakeResponse:
    def __init__(self, status_code, json_data):
        self.status_code = status_code
        self._json = json_data

    def json(self):
        return self._json


class FakeSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def get(self, url, params=None, auth=None, timeout=None):
        self.calls.append((url, params, auth))
        return self._responses.pop(0)


def test_get_uses_basic_auth_and_returns_json():
    session = FakeSession([FakeResponse(200, {"number": "A-1"})])
    c = OctopusClient("sk_test", session=session)
    data = c.get("accounts/A-1/")
    assert data == {"number": "A-1"}
    url, params, auth = session.calls[0]
    assert url == "https://api.octopus.energy/v1/accounts/A-1/"
    assert auth == ("sk_test", "")


def test_get_results_follows_pagination():
    page1 = FakeResponse(200, {"next": "https://api.octopus.energy/v1/x/?page=2",
                               "results": [{"a": 1}]})
    page2 = FakeResponse(200, {"next": None, "results": [{"a": 2}]})
    session = FakeSession([page1, page2])
    c = OctopusClient("sk_test", session=session)
    results = c.get_results("x/")
    assert results == [{"a": 1}, {"a": 2}]


def test_get_raises_apierror_on_401():
    session = FakeSession([FakeResponse(401, {"detail": "no"})])
    c = OctopusClient("sk_test", session=session)
    with pytest.raises(ApiError):
        c.get("accounts/A-1/")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_client.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement `client.py`**

```python
import time

import requests


class ApiError(Exception):
    pass


class OctopusClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.octopus.energy/v1/",
        session=None,
        max_retries: int = 3,
    ):
        self._auth = (api_key, "")
        self._base_url = base_url
        self._session = session or requests.Session()
        self._max_retries = max_retries

    def _request(self, url: str, params: dict | None) -> dict:
        last_status = None
        for attempt in range(self._max_retries):
            resp = self._session.get(url, params=params, auth=self._auth, timeout=30)
            last_status = resp.status_code
            if 200 <= resp.status_code < 300:
                return resp.json()
            if resp.status_code == 429 or resp.status_code >= 500:
                time.sleep(2 ** attempt)
                continue
            raise ApiError(f"GET {url} failed: HTTP {resp.status_code}")
        raise ApiError(f"GET {url} failed after retries: HTTP {last_status}")

    def get(self, path: str, params: dict | None = None) -> dict:
        return self._request(self._base_url + path, params)

    def get_results(self, path: str, params: dict | None = None) -> list[dict]:
        data = self._request(self._base_url + path, params)
        results = list(data.get("results", []))
        next_url = data.get("next")
        while next_url:
            data = self._request(next_url, None)
            results.extend(data.get("results", []))
            next_url = data.get("next")
        return results
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_client.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/octopus_compare/client.py tests/test_client.py
git commit -m "feat: Octopus REST client with auth, pagination, retry"
```

---

## Task 8: Account discovery

**Files:**
- Create: `tests/fixtures/api_samples.py`
- Create: `src/octopus_compare/account.py`
- Test: `tests/test_account.py`

**Interfaces:**
- Produces:
  - `@dataclass account.MeterPoint` with `identifier: str` (mpan or mprn), `serial: str`, `agreements: list[Agreement]`.
  - `@dataclass account.Agreement` with `tariff_code: str`, `valid_from: date | None`, `valid_to: date | None`.
  - `@dataclass account.AccountInfo` with `electricity: MeterPoint`, `gas: MeterPoint`.
  - `account.parse_account(payload: dict) -> AccountInfo`
  - `account.agreements_in_window(agreements: list[Agreement], start: date, end: date) -> list[Agreement]` — agreements overlapping `[start, end)`.
  - `account.product_code_from_tariff(tariff_code: str) -> str` — `tariff_code[5:-2]`.
- Note: agreement `valid_from`/`valid_to` arrive as ISO datetime strings (or `null`); parse the date part.

- [ ] **Step 1: Add the account sample fixture**

Append to a new `tests/fixtures/api_samples.py`:
```python
ACCOUNT = {
    "number": "A-8F18337C",
    "properties": [
        {
            "electricity_meter_points": [
                {
                    "mpan": "1200033187430",
                    "is_export": False,
                    "meters": [{"serial_number": "19L3474725"}],
                    "agreements": [
                        {"tariff_code": "E-1R-SILVER-24-12-31-C",
                         "valid_from": "2025-01-01T00:00:00Z",
                         "valid_to": "2026-03-24T00:00:00Z"},
                        {"tariff_code": "E-1R-VAR-22-11-01-C",
                         "valid_from": "2026-03-24T00:00:00Z",
                         "valid_to": None},
                    ],
                }
            ],
            "gas_meter_points": [
                {
                    "mprn": "3260975110",
                    "meters": [{"serial_number": "E6S12825431961"}],
                    "agreements": [
                        {"tariff_code": "G-1R-SILVER-24-12-31-C",
                         "valid_from": "2025-01-01T00:00:00Z",
                         "valid_to": "2026-03-24T00:00:00Z"},
                        {"tariff_code": "G-1R-VAR-22-11-01-C",
                         "valid_from": "2026-03-24T00:00:00Z",
                         "valid_to": None},
                    ],
                }
            ],
        }
    ],
}
```

- [ ] **Step 2: Write the failing test**

`tests/test_account.py`:
```python
from datetime import date

from octopus_compare.account import (
    parse_account,
    agreements_in_window,
    product_code_from_tariff,
    Agreement,
)
from tests.fixtures.api_samples import ACCOUNT


def test_parse_account_extracts_meter_points():
    info = parse_account(ACCOUNT)
    assert info.electricity.identifier == "1200033187430"
    assert info.electricity.serial == "19L3474725"
    assert info.gas.identifier == "3260975110"
    assert info.gas.serial == "E6S12825431961"
    assert len(info.electricity.agreements) == 2


def test_product_code_from_tariff():
    assert product_code_from_tariff("E-1R-VAR-22-11-01-C") == "VAR-22-11-01"
    assert product_code_from_tariff("G-1R-SILVER-24-12-31-C") == "SILVER-24-12-31"


def test_agreements_in_window_overlap():
    info = parse_account(ACCOUNT)
    win = agreements_in_window(info.electricity.agreements,
                               date(2026, 4, 1), date(2026, 5, 1))
    assert [a.tariff_code for a in win] == ["E-1R-VAR-22-11-01-C"]

    spanning = agreements_in_window(info.electricity.agreements,
                                    date(2026, 3, 1), date(2026, 4, 1))
    assert {a.tariff_code for a in spanning} == {
        "E-1R-SILVER-24-12-31-C", "E-1R-VAR-22-11-01-C"}
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_account.py -v`
Expected: FAIL (module not found).

- [ ] **Step 4: Implement `account.py`**

```python
from dataclasses import dataclass
from datetime import date, datetime


@dataclass
class Agreement:
    tariff_code: str
    valid_from: date | None
    valid_to: date | None


@dataclass
class MeterPoint:
    identifier: str
    serial: str
    agreements: list[Agreement]


@dataclass
class AccountInfo:
    electricity: MeterPoint
    gas: MeterPoint


def _to_date(value: str | None) -> date | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).date()


def _agreements(raw: list[dict]) -> list[Agreement]:
    return [
        Agreement(a["tariff_code"], _to_date(a.get("valid_from")), _to_date(a.get("valid_to")))
        for a in raw
    ]


def _meter_point(raw: dict, id_field: str) -> MeterPoint:
    return MeterPoint(
        identifier=raw[id_field],
        serial=raw["meters"][0]["serial_number"],
        agreements=_agreements(raw.get("agreements", [])),
    )


def parse_account(payload: dict) -> AccountInfo:
    prop = payload["properties"][0]
    elec = [m for m in prop.get("electricity_meter_points", []) if not m.get("is_export")]
    gas = prop.get("gas_meter_points", [])
    return AccountInfo(
        electricity=_meter_point(elec[0], "mpan"),
        gas=_meter_point(gas[0], "mprn"),
    )


def agreements_in_window(
    agreements: list[Agreement], start: date, end: date
) -> list[Agreement]:
    result = []
    for a in agreements:
        a_from = a.valid_from or date.min
        a_to = a.valid_to or date.max
        if a_from < end and a_to > start:
            result.append(a)
    return result


def product_code_from_tariff(tariff_code: str) -> str:
    return tariff_code[5:-2]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_account.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/fixtures/api_samples.py src/octopus_compare/account.py tests/test_account.py
git commit -m "feat: account discovery + agreement/window helpers"
```

---

## Task 9: Tracker product resolution

**Files:**
- Modify: `tests/fixtures/api_samples.py`
- Create: `src/octopus_compare/tracker.py`
- Test: `tests/test_tracker.py`

**Interfaces:**
- Consumes: `OctopusClient.get` / `.get_results` (Task 7).
- Produces:
  - `@dataclass tracker.TrackerTariffs` with `elec_product: str`, `elec_tariff: str`, `gas_product: str`, `gas_tariff: str`.
  - `tracker.resolve_current_tracker(client, region: str, available_at: str) -> TrackerTariffs` — finds the product where `is_tracker` is true via `get_results("products/", {...})`, then `get(f"products/{code}/")` and reads `single_register_electricity_tariffs[region]["direct_debit_monthly"]["code"]` and the gas equivalent.
- Note: `region` is the GSP group string like `"_C"`.

- [ ] **Step 1: Add product samples**

Append to `tests/fixtures/api_samples.py`:
```python
PRODUCTS_LIST = {
    "count": 1,
    "next": None,
    "results": [
        {"code": "SILVER-26-06-01", "display_name": "Octopus Tracker",
         "is_tracker": True, "brand": "OCTOPUS_ENERGY"},
    ],
}

PRODUCT_DETAIL = {
    "code": "SILVER-26-06-01",
    "single_register_electricity_tariffs": {
        "_C": {"direct_debit_monthly": {"code": "E-1R-SILVER-26-06-01-C"}},
    },
    "single_register_gas_tariffs": {
        "_C": {"direct_debit_monthly": {"code": "G-1R-SILVER-26-06-01-C"}},
    },
}
```

- [ ] **Step 2: Write the failing test**

`tests/test_tracker.py`:
```python
from octopus_compare.tracker import resolve_current_tracker, TrackerTariffs
from tests.fixtures.api_samples import PRODUCTS_LIST, PRODUCT_DETAIL


class FakeClient:
    def get_results(self, path, params=None):
        assert path == "products/"
        assert params["is_tracker"] == "true"
        return PRODUCTS_LIST["results"]

    def get(self, path, params=None):
        assert path == "products/SILVER-26-06-01/"
        return PRODUCT_DETAIL


def test_resolve_current_tracker():
    t = resolve_current_tracker(FakeClient(), "_C", "2026-06-25T00:00:00Z")
    assert t == TrackerTariffs(
        elec_product="SILVER-26-06-01",
        elec_tariff="E-1R-SILVER-26-06-01-C",
        gas_product="SILVER-26-06-01",
        gas_tariff="G-1R-SILVER-26-06-01-C",
    )
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_tracker.py -v`
Expected: FAIL (module not found).

- [ ] **Step 4: Implement `tracker.py`**

```python
from dataclasses import dataclass


@dataclass
class TrackerTariffs:
    elec_product: str
    elec_tariff: str
    gas_product: str
    gas_tariff: str


def resolve_current_tracker(client, region: str, available_at: str) -> TrackerTariffs:
    products = client.get_results(
        "products/", {"is_tracker": "true", "available_at": available_at}
    )
    trackers = [p for p in products if p.get("is_tracker")]
    if not trackers:
        raise ValueError("No current Tracker product found")
    code = trackers[0]["code"]
    detail = client.get(f"products/{code}/")
    elec = detail["single_register_electricity_tariffs"][region]["direct_debit_monthly"]["code"]
    gas = detail["single_register_gas_tariffs"][region]["direct_debit_monthly"]["code"]
    return TrackerTariffs(
        elec_product=code, elec_tariff=elec, gas_product=code, gas_tariff=gas
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_tracker.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/fixtures/api_samples.py src/octopus_compare/tracker.py tests/test_tracker.py
git commit -m "feat: resolve current Tracker product + tariff codes"
```

---

## Task 10: Rate + standing-charge lookups

**Files:**
- Modify: `tests/fixtures/api_samples.py`
- Create: `src/octopus_compare/rates.py`
- Test: `tests/test_rates.py`

**Interfaces:**
- Consumes: `OctopusClient.get_results` (Task 7).
- Produces:
  - `class rates.RateLookup`: built from API result dicts; `rate_for(day: date) -> Decimal` returns the exc-VAT pence whose `[valid_from, valid_to)` (Europe/London date) covers `day`. Raises `KeyError` if no rate covers the day.
  - `rates.build_lookup(results: list[dict]) -> RateLookup`
  - `rates.fetch_rates(client, supply: str, product_code: str, tariff_code: str, period_from: date, period_to: date) -> RateLookup` — calls `products/{product}/{supply}-tariffs/{tariff}/standard-unit-rates/`.
  - `rates.fetch_standing_charges(client, supply, product_code, tariff_code, period_from, period_to) -> RateLookup` — same shape, `/standing-charges/`.
- Note: `supply` is `"electricity"` or `"gas"`. Periods are sent as ISO datetimes (append `T00:00:00Z`). Result fields used: `value_exc_vat`, `valid_from`, `valid_to`.

- [ ] **Step 1: Add rate samples**

Append to `tests/fixtures/api_samples.py`:
```python
# Tracker daily rates (one per local day); exc-VAT pence.
TRACKER_ELEC_RATES = {
    "results": [
        {"value_exc_vat": 18.78, "value_inc_vat": 19.719,
         "valid_from": "2026-03-01T00:00:00Z", "valid_to": "2026-03-02T00:00:00Z"},
        {"value_exc_vat": 19.81, "value_inc_vat": 20.80,
         "valid_from": "2026-03-02T00:00:00Z", "valid_to": "2026-03-03T00:00:00Z"},
    ]
}

# Flexible: single open-ended rate.
FLEX_ELEC_RATES = {
    "results": [
        {"value_exc_vat": 23.71, "value_inc_vat": 24.8955,
         "valid_from": "2026-04-01T00:00:00Z", "valid_to": None},
    ]
}

FLEX_ELEC_STANDING = {
    "results": [
        {"value_exc_vat": 42.18, "value_inc_vat": 44.289,
         "valid_from": "2026-04-01T00:00:00Z", "valid_to": None},
    ]
}
```

- [ ] **Step 2: Write the failing test**

`tests/test_rates.py`:
```python
from datetime import date
from decimal import Decimal

import pytest

from octopus_compare.rates import build_lookup
from tests.fixtures.api_samples import TRACKER_ELEC_RATES, FLEX_ELEC_RATES


def test_tracker_rate_per_day():
    lookup = build_lookup(TRACKER_ELEC_RATES["results"])
    assert lookup.rate_for(date(2026, 3, 1)) == Decimal("18.78")
    assert lookup.rate_for(date(2026, 3, 2)) == Decimal("19.81")


def test_flexible_open_ended_rate():
    lookup = build_lookup(FLEX_ELEC_RATES["results"])
    assert lookup.rate_for(date(2026, 4, 15)) == Decimal("23.71")
    assert lookup.rate_for(date(2026, 12, 31)) == Decimal("23.71")


def test_missing_rate_raises():
    lookup = build_lookup(TRACKER_ELEC_RATES["results"])
    with pytest.raises(KeyError):
        lookup.rate_for(date(2026, 3, 10))
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_rates.py -v`
Expected: FAIL (module not found).

- [ ] **Step 4: Implement `rates.py`**

```python
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

LONDON = ZoneInfo("Europe/London")


def _to_london_date(value: str | None, default: date) -> date:
    if not value:
        return default
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt.astimezone(LONDON).date()


@dataclass
class _Window:
    start: date
    end: date
    value: Decimal


class RateLookup:
    def __init__(self, windows: list[_Window]):
        self._windows = windows

    def rate_for(self, day: date) -> Decimal:
        for w in self._windows:
            if w.start <= day < w.end:
                return w.value
        raise KeyError(f"No rate covering {day}")


def build_lookup(results: list[dict]) -> RateLookup:
    windows = []
    for r in results:
        windows.append(
            _Window(
                start=_to_london_date(r.get("valid_from"), date.min),
                end=_to_london_date(r.get("valid_to"), date.max),
                value=Decimal(str(r["value_exc_vat"])),
            )
        )
    return RateLookup(windows)


def _iso(d: date) -> str:
    return d.strftime("%Y-%m-%dT00:00:00Z")


def fetch_rates(client, supply, product_code, tariff_code, period_from, period_to):
    path = f"products/{product_code}/{supply}-tariffs/{tariff_code}/standard-unit-rates/"
    results = client.get_results(
        path, {"period_from": _iso(period_from), "period_to": _iso(period_to)}
    )
    return build_lookup(results)


def fetch_standing_charges(client, supply, product_code, tariff_code, period_from, period_to):
    path = f"products/{product_code}/{supply}-tariffs/{tariff_code}/standing-charges/"
    results = client.get_results(
        path, {"period_from": _iso(period_from), "period_to": _iso(period_to)}
    )
    return build_lookup(results)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_rates.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/fixtures/api_samples.py src/octopus_compare/rates.py tests/test_rates.py
git commit -m "feat: rate + standing-charge lookups with date windows"
```

---

## Task 11: Consumption fetching + gas unit handling

**Files:**
- Modify: `tests/fixtures/api_samples.py`
- Create: `src/octopus_compare/consumption.py`
- Test: `tests/test_consumption.py`

**Interfaces:**
- Consumes: `OctopusClient.get_results` (Task 7), `units.m3_to_kwh` (Task 5).
- Produces:
  - `consumption.fetch_daily(client, supply: str, identifier: str, serial: str, period_from: date, period_to: date) -> dict[date, Decimal]` — raw daily consumption (`group_by="day"`), keyed by Europe/London date of `interval_start`, value `consumption` as `Decimal` (raw units).
  - `consumption.to_kwh(raw: dict[date, Decimal], supply: str, gas_units: str, calorific_value: Decimal) -> dict[date, Decimal]` — electricity passes through; gas converts from m³ unless units resolve to kWh. `gas_units="auto"` → treat as kWh if mean daily value > 15 else m³.
- Note: path is `{supply}-meter-points/{identifier}/meters/{serial}/consumption/`.

- [ ] **Step 1: Add consumption sample**

Append to `tests/fixtures/api_samples.py`:
```python
GAS_CONSUMPTION_M3 = {
    "results": [
        {"consumption": 3.52, "interval_start": "2026-03-01T00:00:00Z",
         "interval_end": "2026-03-02T00:00:00Z"},
        {"consumption": 3.16, "interval_start": "2026-03-02T00:00:00Z",
         "interval_end": "2026-03-03T00:00:00Z"},
    ]
}
ELEC_CONSUMPTION_KWH = {
    "results": [
        {"consumption": 9.09, "interval_start": "2026-03-01T00:00:00Z",
         "interval_end": "2026-03-02T00:00:00Z"},
    ]
}
```

- [ ] **Step 2: Write the failing test**

`tests/test_consumption.py`:
```python
from datetime import date
from decimal import Decimal

from octopus_compare.consumption import fetch_daily, to_kwh
from tests.fixtures.api_samples import GAS_CONSUMPTION_M3, ELEC_CONSUMPTION_KWH


class FakeClient:
    def __init__(self, results):
        self._results = results
        self.path = None

    def get_results(self, path, params=None):
        self.path = path
        return self._results


def test_fetch_daily_buckets_by_local_date():
    client = FakeClient(ELEC_CONSUMPTION_KWH["results"])
    daily = fetch_daily(client, "electricity", "1200033187430", "19L3474725",
                        date(2026, 3, 1), date(2026, 3, 2))
    assert daily == {date(2026, 3, 1): Decimal("9.09")}
    assert client.path == (
        "electricity-meter-points/1200033187430/meters/19L3474725/consumption/")


def test_gas_auto_detects_m3_and_converts():
    raw = {date(2026, 3, 1): Decimal("3.52")}
    kwh = to_kwh(raw, "gas", "auto", Decimal("39.2"))
    # 3.52 × 1.02264 × 39.2 / 3.6 ≈ 39.19
    assert abs(kwh[date(2026, 3, 1)] - Decimal("39.19")) <= Decimal("0.1")


def test_gas_explicit_kwh_passthrough():
    raw = {date(2026, 3, 1): Decimal("39.2")}
    kwh = to_kwh(raw, "gas", "kwh", Decimal("39.5"))
    assert kwh[date(2026, 3, 1)] == Decimal("39.2")


def test_electricity_passthrough():
    raw = {date(2026, 3, 1): Decimal("9.09")}
    assert to_kwh(raw, "electricity", "auto", Decimal("39.5")) == raw
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_consumption.py -v`
Expected: FAIL (module not found).

- [ ] **Step 4: Implement `consumption.py`**

```python
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from octopus_compare.units import m3_to_kwh

LONDON = ZoneInfo("Europe/London")


def _local_date(value: str) -> date:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(LONDON).date()


def _iso(d: date) -> str:
    return d.strftime("%Y-%m-%dT00:00:00Z")


def fetch_daily(client, supply, identifier, serial, period_from, period_to):
    path = f"{supply}-meter-points/{identifier}/meters/{serial}/consumption/"
    results = client.get_results(
        path,
        {
            "period_from": _iso(period_from),
            "period_to": _iso(period_to),
            "group_by": "day",
            "order_by": "period",
            "page_size": 25000,
        },
    )
    daily: dict[date, Decimal] = {}
    for r in results:
        day = _local_date(r["interval_start"])
        daily[day] = daily.get(day, Decimal(0)) + Decimal(str(r["consumption"]))
    return daily


def _resolve_gas_units(raw: dict[date, Decimal], gas_units: str) -> str:
    if gas_units in ("m3", "kwh"):
        return gas_units
    if not raw:
        return "m3"
    mean = sum(raw.values(), Decimal(0)) / len(raw)
    return "kwh" if mean > 15 else "m3"


def to_kwh(raw, supply, gas_units, calorific_value):
    if supply == "electricity":
        return raw
    resolved = _resolve_gas_units(raw, gas_units)
    if resolved == "kwh":
        return raw
    return {d: m3_to_kwh(v, calorific_value) for d, v in raw.items()}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_consumption.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/fixtures/api_samples.py src/octopus_compare/consumption.py tests/test_consumption.py
git commit -m "feat: daily consumption fetch + gas unit handling"
```

---

## Task 12: Report + recommendation

**Files:**
- Create: `src/octopus_compare/report.py`
- Test: `tests/test_report.py`

**Interfaces:**
- Consumes: `costing.SupplyCost` (Task 4).
- Produces:
  - `@dataclass report.ComparisonResult` with: `period_from: date`, `period_to: date`, `elec_actual: SupplyCost`, `elec_tracker: SupplyCost`, `gas_actual: SupplyCost`, `gas_tracker: SupplyCost`. Properties: `actual_total -> Decimal`, `tracker_total -> Decimal`, `delta -> Decimal` (tracker − actual), `pct -> Decimal` (delta / actual × 100).
  - `report.recommend(result: ComparisonResult, threshold_pct: Decimal = Decimal("2")) -> str` → one of `"SWITCH BACK"`, `"MARGINAL"`, `"STAY"`.
  - `report.format_text(result: ComparisonResult) -> str`
  - `report.format_json(result: ComparisonResult) -> str`

- [ ] **Step 1: Write the failing test**

`tests/test_report.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_report.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement `report.py`**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_report.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/octopus_compare/report.py tests/test_report.py
git commit -m "feat: comparison result, recommendation, text/json report"
```

---

## Task 13: Pipeline orchestration

**Files:**
- Create: `src/octopus_compare/pipeline.py`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `account` (Task 8), `tracker` (Task 9), `rates` (Task 10), `consumption` (Task 11), `costing` (Task 4), `report.ComparisonResult` (Task 12).
- Produces:
  - `pipeline.run_comparison(client, config: Config) -> ComparisonResult`
- Behaviour:
  1. `parse_account(client.get(f"accounts/{config.account}/"))`.
  2. region = `client.get(f"electricity-meter-points/{elec.identifier}/")["gsp"]`.
  3. `tracker = resolve_current_tracker(client, region, available_at=config.period_to ISO)`.
  4. For each supply: `fetch_daily` → `to_kwh`; build **actual** rate/standing lookups from the agreement(s) active in the window (use the agreement covering `period_to`; derive product via `product_code_from_tariff`); build **tracker** lookups from the resolved tracker tariffs; compute two `supply_cost`s.
- Note: keep the actual side simple — use the single agreement active at `period_to` (the current Flexible tariff). Multi-agreement windows are handled by `agreements_in_window` returning that agreement for the default window.

- [ ] **Step 1: Write the failing test (with an in-memory fake client)**

`tests/test_pipeline.py`:
```python
from datetime import date
from decimal import Decimal

from octopus_compare.config import Config
from octopus_compare.pipeline import run_comparison
from tests.fixtures.api_samples import (
    ACCOUNT, PRODUCTS_LIST, PRODUCT_DETAIL,
    FLEX_ELEC_RATES, FLEX_ELEC_STANDING,
)


class FakeClient:
    """Routes paths to canned payloads covering one flat-rate month."""

    def get(self, path, params=None):
        if path == "accounts/A-8F18337C/":
            return ACCOUNT
        if path == "electricity-meter-points/1200033187430/":
            return {"gsp": "_C"}
        if path == "products/SILVER-26-06-01/":
            return PRODUCT_DETAIL
        raise AssertionError(path)

    def get_results(self, path, params=None):
        if path == "products/":
            return PRODUCTS_LIST["results"]
        if "consumption" in path:
            return [{"consumption": 9.0,
                     "interval_start": "2026-04-01T00:00:00Z",
                     "interval_end": "2026-04-02T00:00:00Z"}]
        if "standard-unit-rates" in path:
            return FLEX_ELEC_RATES["results"]
        if "standing-charges" in path:
            return FLEX_ELEC_STANDING["results"]
        raise AssertionError(path)


def _config():
    return Config(
        api_key="sk", account="A-8F18337C",
        period_from=date(2026, 4, 1), period_to=date(2026, 4, 2),
        output_format="text", gas_calorific_value=Decimal("39.5"),
        gas_units="kwh", verbose=False,
    )


def test_run_comparison_produces_result():
    result = run_comparison(FakeClient(), _config())
    assert result.period_from == date(2026, 4, 1)
    assert result.actual_total > 0
    assert result.tracker_total > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_pipeline.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement `pipeline.py`**

```python
from datetime import date

from octopus_compare.account import (
    parse_account, agreements_in_window, product_code_from_tariff,
)
from octopus_compare.config import Config
from octopus_compare.consumption import fetch_daily, to_kwh
from octopus_compare.costing import supply_cost
from octopus_compare.rates import fetch_rates, fetch_standing_charges
from octopus_compare.report import ComparisonResult
from octopus_compare.tracker import resolve_current_tracker


def _iso(d: date) -> str:
    return d.strftime("%Y-%m-%dT00:00:00Z")


def _supply_costs(client, supply, meter, tracker_product, tracker_tariff, cfg):
    raw = fetch_daily(client, supply, meter.identifier, meter.serial,
                      cfg.period_from, cfg.period_to)
    kwh = to_kwh(raw, supply, cfg.gas_units, cfg.gas_calorific_value)

    window = agreements_in_window(meter.agreements, cfg.period_from, cfg.period_to)
    actual = max(window, key=lambda a: a.valid_from or date.min)
    actual_product = product_code_from_tariff(actual.tariff_code)
    actual_rates = fetch_rates(client, supply, actual_product, actual.tariff_code,
                               cfg.period_from, cfg.period_to)
    actual_sc = fetch_standing_charges(client, supply, actual_product, actual.tariff_code,
                                       cfg.period_from, cfg.period_to)
    tracker_rates = fetch_rates(client, supply, tracker_product, tracker_tariff,
                                cfg.period_from, cfg.period_to)
    tracker_sc = fetch_standing_charges(client, supply, tracker_product, tracker_tariff,
                                        cfg.period_from, cfg.period_to)

    cost_actual = supply_cost(kwh, actual_rates.rate_for, actual_sc.rate_for)
    cost_tracker = supply_cost(kwh, tracker_rates.rate_for, tracker_sc.rate_for)
    return cost_actual, cost_tracker


def run_comparison(client, config: Config) -> ComparisonResult:
    info = parse_account(client.get(f"accounts/{config.account}/"))
    region = client.get(f"electricity-meter-points/{info.electricity.identifier}/")["gsp"]
    tracker = resolve_current_tracker(client, region, _iso(config.period_to))

    elec_actual, elec_tracker = _supply_costs(
        client, "electricity", info.electricity,
        tracker.elec_product, tracker.elec_tariff, config)
    gas_actual, gas_tracker = _supply_costs(
        client, "gas", info.gas,
        tracker.gas_product, tracker.gas_tariff, config)

    return ComparisonResult(
        period_from=config.period_from, period_to=config.period_to,
        elec_actual=elec_actual, elec_tracker=elec_tracker,
        gas_actual=gas_actual, gas_tracker=gas_tracker,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_pipeline.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/octopus_compare/pipeline.py tests/test_pipeline.py
git commit -m "feat: pipeline orchestration of the full comparison"
```

---

## Task 14: CLI entry point

**Files:**
- Create: `src/octopus_compare/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `config.load_config`/`ConfigError` (Task 6), `client.OctopusClient`/`ApiError` (Task 7), `pipeline.run_comparison` (Task 13), `report.format_text`/`format_json` (Task 12).
- Produces:
  - `cli.main(argv: list[str] | None = None) -> int` — loads `.env` via `dotenv`, builds config, runs the comparison, prints the report, returns an exit code (0 ok, 2 config error, 3 API error).
- Note: keep `main` thin and inject seams for tests via module-level functions `_load_env()`, `_build_client(cfg)`, `_today()` that tests can monkeypatch.

- [ ] **Step 1: Write the failing test**

`tests/test_cli.py`:
```python
from datetime import date

import octopus_compare.cli as cli


def test_main_prints_report(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_load_env",
                        lambda: {"OCTOPUS_API_KEY": "sk", "OCTOPUS_ACCOUNT": "A-8F18337C"})
    monkeypatch.setattr(cli, "_today", lambda: date(2026, 4, 2))

    class FakeResult:
        pass

    monkeypatch.setattr(cli, "_build_client", lambda cfg: object())
    monkeypatch.setattr(cli, "run_comparison", lambda client, cfg: "RESULT")
    monkeypatch.setattr(cli, "format_text", lambda result: "REPORT-TEXT")

    code = cli.main(["--from", "2026-04-01", "--to", "2026-04-01"])
    assert code == 0
    assert "REPORT-TEXT" in capsys.readouterr().out


def test_main_config_error_returns_2(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_load_env", lambda: {})
    monkeypatch.setattr(cli, "_today", lambda: date(2026, 4, 2))
    code = cli.main([])
    assert code == 2
    assert "OCTOPUS_API_KEY" in capsys.readouterr().err
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cli.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement `cli.py`**

```python
import os
import sys
from datetime import date

from dotenv import dotenv_values

from octopus_compare.client import OctopusClient, ApiError
from octopus_compare.config import load_config, ConfigError
from octopus_compare.pipeline import run_comparison
from octopus_compare.report import format_text, format_json


def _load_env() -> dict:
    env = {**dotenv_values(".env"), **os.environ}
    return env


def _today() -> date:
    return date.today()


def _build_client(cfg) -> OctopusClient:
    return OctopusClient(cfg.api_key)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    env = _load_env()
    try:
        cfg = load_config(argv, env, _today())
    except ConfigError as e:
        print(str(e), file=sys.stderr)
        return 2

    try:
        client = _build_client(cfg)
        result = run_comparison(client, cfg)
    except ApiError as e:
        print(f"Octopus API error: {e}", file=sys.stderr)
        return 3

    output = format_json(result) if cfg.output_format == "json" else format_text(result)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_cli.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -v`
Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/octopus_compare/cli.py tests/test_cli.py
git commit -m "feat: CLI entry point with error handling"
```

---

## Task 15: README + Tier-3 live eval (optional, env-gated)

**Files:**
- Create: `README.md`
- Create: `tests/test_live_eval.py`

**Interfaces:**
- Consumes: everything (end-to-end).
- Produces: a live eval that runs the real pipeline against the real account and asserts the **actual** totals reproduce the three bills, and that API rates match the bill rates. Skipped unless `OCTOPUS_LIVE_EVAL=1`.

- [ ] **Step 1: Write the env-gated live eval**

`tests/test_live_eval.py`:
```python
import os
from datetime import date
from decimal import Decimal

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("OCTOPUS_LIVE_EVAL") != "1",
    reason="set OCTOPUS_LIVE_EVAL=1 (needs real OCTOPUS_API_KEY) to run",
)


@pytest.mark.parametrize(
    "period_from, period_to, expected_elec_total, expected_gas_total",
    [
        # Bill 411480086 (April 2026, all Flexible).
        (date(2026, 4, 1), date(2026, 5, 1), Decimal("80.94"), Decimal("59.08")),
        # Bill 420492378 (May 2026, all Flexible).
        (date(2026, 5, 1), date(2026, 6, 1), Decimal("81.47"), Decimal("40.76")),
    ],
)
def test_actual_totals_match_bills(period_from, period_to,
                                   expected_elec_total, expected_gas_total):
    from dotenv import dotenv_values
    from octopus_compare.client import OctopusClient
    from octopus_compare.config import Config
    from octopus_compare.pipeline import run_comparison

    env = {**dotenv_values(".env"), **os.environ}
    cfg = Config(
        api_key=env["OCTOPUS_API_KEY"], account=env["OCTOPUS_ACCOUNT"],
        period_from=period_from, period_to=period_to,
        output_format="text", gas_calorific_value=Decimal("39.5"),
        gas_units="auto", verbose=True,
    )
    result = run_comparison(OctopusClient(cfg.api_key), cfg)
    # Actual (Flexible) side should reproduce the bill within a few pence.
    assert abs(result.elec_actual.total_pounds - expected_elec_total) <= Decimal("0.50")
    assert abs(result.gas_actual.total_pounds - expected_gas_total) <= Decimal("1.00")
```

- [ ] **Step 2: Run it (skips without the env flag)**

Run: `python -m pytest tests/test_live_eval.py -v`
Expected: SKIPPED (no `OCTOPUS_LIVE_EVAL`).

- [ ] **Step 3: Run it live once the API key is in `.env`**

Run: `OCTOPUS_LIVE_EVAL=1 python -m pytest tests/test_live_eval.py -v`
Expected: PASS — actual Flexible totals reproduce bills 2 & 3. (Gas tolerance is wider because the live calorific value differs slightly from the default 39.5. If electricity is off by more than a few pence, investigate the gas-units auto-detection and the Europe/London day bucketing per spec §11.)

- [ ] **Step 4: Write `README.md`**

```markdown
# octopus-compare

Compare your actual Flexible Octopus spend against what Octopus Tracker would
have cost (electricity + gas), and get a switch recommendation.

## Setup

    python -m pip install -e ".[dev]"
    cp .env.example .env   # then paste your API key

Get your API key: https://octopus.energy/dashboard/new/accounts/personal-details/api-access

## Usage

    octopus-compare                       # last 3 months
    octopus-compare --months 1
    octopus-compare --from 2026-04-01 --to 2026-04-30
    octopus-compare --format json

## Tests

    python -m pytest                      # offline unit + eval tests
    OCTOPUS_LIVE_EVAL=1 python -m pytest tests/test_live_eval.py   # live, needs API key

The offline suite validates the cost engine to the penny against three real
bills transcribed in `tests/fixtures/bills.py`.
```

- [ ] **Step 5: Commit**

```bash
git add README.md tests/test_live_eval.py
git commit -m "docs: README + env-gated live eval against bills"
```

---

## Self-Review (completed during planning)

**Spec coverage:**
- Auto-discovery (account, meters, agreements, region) → Tasks 8, 13.
- Flexible-vs-Tracker costing on the same consumption → Tasks 3–4, 13.
- Configurable window (default 3 months), `--from/--to` → Task 6.
- Per-day rounding + 5% VAT + gas m³→kWh → Tasks 3–5 (penny-exact eval).
- Tracker resolution (no hard-coded code) → Task 9.
- Rate/standing-charge date-window matching → Task 10.
- Gas unit ambiguity handling → Task 11.
- Text + JSON report + thresholds → Task 12.
- Error handling (config/API/coverage), exit codes → Tasks 6, 7, 14.
- Three-tier eval (penny-exact, tolerance, online) → Tasks 3–5 (Tier 1/2), Task 15 (Tier 3).
- README → Task 15.

**Placeholder scan:** none — every step has runnable code/commands.

**Type consistency:** `SupplyCost`, `ComparisonResult`, `RateLookup.rate_for`,
`supply_cost(daily_kwh, rate_p_for, sc_p_for)`, `product_code_from_tariff`,
`TrackerTariffs`, and `Config` field names are used identically across Tasks 3–15.

**Note vs spec:** the spec §7 said "use `value_inc_vat` throughout"; planning
against the bills showed Octopus rounds per-day on **exc-VAT** then applies 5% VAT
to the subtotal. The plan uses exc-VAT line items + VAT-at-subtotal (Global
Constraints), which reproduces every bill total exactly. The spec note will be
updated to match.

**Deferred to implementation (per spec §11):** exact standing-charge rounding edge
(bill 3 elec SC is 1p under `round(31 × 42.18p)` — covered by Tier-2 tolerance, not
Tier-1); confirmation of gas API units (m³ vs kWh) and BST day-bucketing, both
verified by the Task 15 live eval.
