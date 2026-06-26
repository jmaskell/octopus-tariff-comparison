# Flexible-vs-Agile Comparison Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an `octopus-compare agile` subcommand that backtests real half-hourly electricity usage against Octopus Agile's published half-hourly rates, alongside the Flexible baseline, with a time-of-use insight block.

**Architecture:** A new, isolated half-hourly path (consumption fetch, datetime-keyed rate lookup, cost engine, insight, pipeline, report) that reuses the existing value primitives (`SupplyCost`, `money.py`, `VersionedLookup`). The penny-validated daily engine (`costing.py`, `rates.py`) is left untouched. The Flexible baseline reuses the existing daily `supply_cost`, so its total matches the main report to the penny.

**Tech Stack:** Python 3.14, `requests`, `python-dotenv`, `pytest`, `Decimal` money math, `zoneinfo`.

## Global Constraints

- **Electricity only.** Agile is electricity-only; gas is excluded from this subcommand entirely.
- **Pricing model: historical backtest.** Real half-hourly usage on each date × the Agile half-hourly rates published for that same date, across every Agile version intersecting the window.
- **Daily engine untouched.** Do not modify `costing.py` or `rates.py` except the additive `flat_lookup`-style helpers already present; the penny-exact bill evals in `test_costing.py` must stay green.
- **UTC-instant alignment.** Half-hourly consumption and Agile rates align by the absolute UTC instant of each half-hour; peak/off-peak classification uses Europe/London local time.
- **Per-day rounding.** Agile energy cost = sum over days of `round_half_up(sum over that day's half-hours of kwh × exc-VAT rate)`, matching the daily engine's one-rounding-per-day convention. VAT is 5% on the subtotal.
- **Money:** all money math in `Decimal`; reuse `round_pence`, `vat_pence`, `pounds` from `money.py`. Rates may be **negative** (plunge pricing).
- **Backward compatibility:** `octopus-compare` with no subcommand must produce the unchanged 3-column daily report.

---

### Task 1: Half-hourly consumption fetch

**Files:**
- Modify: `src/octopus_compare/consumption.py`
- Modify: `tests/fixtures/api_samples.py`
- Test: `tests/test_consumption.py`

**Interfaces:**
- Produces: `fetch_halfhourly(client, identifier, serials, period_from, period_to) -> dict[datetime, Decimal]` — keyed by the **UTC** instant of each half-hour's `interval_start`, summed across serials. Electricity only.

- [ ] **Step 1: Add the fixture**

Add to `tests/fixtures/api_samples.py`:

```python
# Half-hourly electricity consumption (kWh per half hour). Includes a peak slot
# (16:00 London) and a DST-boundary day.
HH_CONSUMPTION = {
    "results": [
        {"consumption": 0.20, "interval_start": "2026-03-01T00:00:00Z",
         "interval_end": "2026-03-01T00:30:00Z"},
        {"consumption": 0.30, "interval_start": "2026-03-01T00:30:00Z",
         "interval_end": "2026-03-01T01:00:00Z"},
        {"consumption": 0.90, "interval_start": "2026-03-01T16:00:00Z",
         "interval_end": "2026-03-01T16:30:00Z"},
        {"consumption": 0.10, "interval_start": "2026-03-01T17:00:00Z",
         "interval_end": "2026-03-01T17:30:00Z"},
    ]
}
```

- [ ] **Step 2: Write the failing test**

Add to `tests/test_consumption.py`:

```python
from datetime import datetime
from zoneinfo import ZoneInfo
from octopus_compare.consumption import fetch_halfhourly
from tests.fixtures.api_samples import HH_CONSUMPTION

_UTC = ZoneInfo("UTC")


def test_fetch_halfhourly_keys_by_utc_instant():
    client = FakeClient(HH_CONSUMPTION["results"])
    half = fetch_halfhourly(client, "1200033187430", ["19L3474725"],
                            date(2026, 3, 1), date(2026, 3, 2))
    assert half[datetime(2026, 3, 1, 0, 0, tzinfo=_UTC)] == Decimal("0.20")
    assert half[datetime(2026, 3, 1, 16, 0, tzinfo=_UTC)] == Decimal("0.90")
    assert len(half) == 4
    assert client.paths == [
        "electricity-meter-points/1200033187430/meters/19L3474725/consumption/"]


def test_fetch_halfhourly_sums_across_meters():
    rows = HH_CONSUMPTION["results"]

    class MultiMeterClient:
        def get_results(self, path, params=None):
            serial = path.split("/meters/")[1].split("/")[0]
            return rows if serial == "NEW" else []

    half = fetch_halfhourly(MultiMeterClient(), "1200033187430", ["OLD", "NEW"],
                            date(2026, 3, 1), date(2026, 3, 2))
    assert half[datetime(2026, 3, 1, 0, 0, tzinfo=_UTC)] == Decimal("0.20")
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_consumption.py::test_fetch_halfhourly_keys_by_utc_instant -v`
Expected: FAIL with `ImportError: cannot import name 'fetch_halfhourly'`

- [ ] **Step 4: Implement**

Add to `src/octopus_compare/consumption.py` (the file already imports `datetime`, `ZoneInfo`, defines `LONDON` and `_iso`):

```python
UTC = ZoneInfo("UTC")


def _utc_instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def fetch_halfhourly(client, identifier, serials, period_from, period_to):
    """Half-hourly electricity consumption summed across the point's serials,
    keyed by the UTC instant of interval_start so it aligns to Agile rate
    windows regardless of GMT/BST. Electricity only."""
    half: dict[datetime, Decimal] = {}
    for serial in serials:
        path = f"electricity-meter-points/{identifier}/meters/{serial}/consumption/"
        results = client.get_results(
            path,
            {
                "period_from": _iso(period_from),
                "period_to": _iso(period_to),
                "order_by": "period",
                "page_size": 25000,
            },
        )
        for r in results:
            instant = _utc_instant(r["interval_start"])
            half[instant] = half.get(instant, Decimal(0)) + Decimal(str(r["consumption"]))
    return half
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_consumption.py -v`
Expected: PASS (all, including the existing daily tests)

- [ ] **Step 6: Commit**

```bash
git add src/octopus_compare/consumption.py tests/test_consumption.py tests/fixtures/api_samples.py
git commit -m "feat: half-hourly consumption fetch keyed by UTC instant"
```

---

### Task 2: Half-hourly rate lookup

**Files:**
- Create: `src/octopus_compare/agile.py`
- Test: `tests/test_agile.py`

**Interfaces:**
- Produces: `HalfHourlyRates` with `.rate_for(instant: datetime) -> Decimal` (raises `KeyError` when no window covers the instant); `build_halfhourly_lookup(results: list[dict]) -> HalfHourlyRates`. Keys are the UTC instant of each window's `valid_from`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_agile.py`:

```python
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from octopus_compare.agile import build_halfhourly_lookup

_UTC = ZoneInfo("UTC")


def test_halfhourly_lookup_by_utc_instant():
    results = [
        {"value_exc_vat": 22.5, "valid_from": "2026-03-01T16:00:00Z",
         "valid_to": "2026-03-01T16:30:00Z"},
        {"value_exc_vat": -1.8, "valid_from": "2026-03-01T13:30:00Z",
         "valid_to": "2026-03-01T14:00:00Z"},
    ]
    rates = build_halfhourly_lookup(results)
    assert rates.rate_for(datetime(2026, 3, 1, 16, 0, tzinfo=_UTC)) == Decimal("22.5")
    assert rates.rate_for(datetime(2026, 3, 1, 13, 30, tzinfo=_UTC)) == Decimal("-1.8")


def test_halfhourly_lookup_aligns_across_timezones():
    # A rate published with a +01:00 (BST) offset is found by the same instant
    # expressed in UTC — proves UTC-instant alignment over DST.
    rates = build_halfhourly_lookup(
        [{"value_exc_vat": 30.0, "valid_from": "2026-03-29T01:00:00+01:00",
          "valid_to": "2026-03-29T01:30:00+01:00"}])
    assert rates.rate_for(datetime(2026, 3, 29, 0, 0, tzinfo=_UTC)) == Decimal("30.0")


def test_halfhourly_lookup_missing_raises():
    rates = build_halfhourly_lookup([])
    with pytest.raises(KeyError):
        rates.rate_for(datetime(2026, 3, 1, 0, 0, tzinfo=_UTC))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_agile.py::test_halfhourly_lookup_by_utc_instant -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'octopus_compare.agile'`

- [ ] **Step 3: Implement**

Create `src/octopus_compare/agile.py`:

```python
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

_UTC = ZoneInfo("UTC")


def _utc_instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(_UTC)


class HalfHourlyRates:
    """Agile unit rates keyed by the UTC instant of each half-hour's valid_from.
    Agile publishes exactly one aligned 30-minute window per slot, so an exact
    instant match is correct (and version windows never overlap, so merging the
    dicts of several versions is unambiguous)."""

    def __init__(self, by_instant: dict[datetime, Decimal]):
        self._by_instant = by_instant

    def rate_for(self, instant: datetime) -> Decimal:
        try:
            return self._by_instant[instant]
        except KeyError as e:
            raise KeyError(f"No Agile rate covering {instant.isoformat()}") from e


def build_halfhourly_lookup(results: list[dict]) -> HalfHourlyRates:
    by_instant: dict[datetime, Decimal] = {}
    for r in results:
        by_instant[_utc_instant(r["valid_from"])] = Decimal(str(r["value_exc_vat"]))
    return HalfHourlyRates(by_instant)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_agile.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/octopus_compare/agile.py tests/test_agile.py
git commit -m "feat: datetime-keyed half-hourly Agile rate lookup"
```

---

### Task 3: Agile version resolution

**Files:**
- Modify: `src/octopus_compare/agile.py`
- Modify: `tests/fixtures/api_samples.py`
- Test: `tests/test_agile.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `AgileVersion(product_code: str, display_name: str, available_from: date, available_to: date | None)`; `resolve_agile_versions(client, period_from, period_to, override=None) -> list[AgileVersion]` (sorted by `available_from`; raises `ValueError` if none intersect the window).

- [ ] **Step 1: Add the fixture**

Add to `tests/fixtures/api_samples.py`:

```python
# Listing payload for resolve_agile_versions (GET /products/?brand=OCTOPUS_ENERGY).
AGILE_PRODUCTS_LIST = [
    {"code": "AGILE-24-10-01", "full_name": "Agile Octopus October 2024 v1",
     "display_name": "Agile Octopus",
     "available_from": "2024-10-01T00:00:00+01:00", "available_to": None},
    {"code": "AGILE-23-12-06", "full_name": "Agile Octopus December 2023 v1",
     "display_name": "Agile Octopus",
     "available_from": "2023-12-06T00:00:00Z", "available_to": "2024-10-01T00:00:00+01:00"},
    {"code": "OE-FIX-12M-26-06-24", "full_name": "Octopus 12M Fixed June 2026 v5",
     "display_name": "Octopus 12M Fixed",
     "available_from": "2026-06-24T00:00:00+01:00", "available_to": None},
]
```

- [ ] **Step 2: Write the failing test**

Add to `tests/test_agile.py`:

```python
from octopus_compare.agile import resolve_agile_versions, AgileVersion
from tests.fixtures.api_samples import AGILE_PRODUCTS_LIST


class AgileListClient:
    def __init__(self, results=AGILE_PRODUCTS_LIST):
        self._results = results

    def get_results(self, path, params=None):
        assert path == "products/"
        return self._results

    def get(self, path, params=None):
        code = path.split("/")[1]
        for r in AGILE_PRODUCTS_LIST:
            if r["code"] == code:
                return r
        raise AssertionError(code)


def test_resolve_agile_versions_filters_to_window():
    versions = resolve_agile_versions(
        AgileListClient(), date(2026, 1, 1), date(2026, 5, 31))
    codes = [v.product_code for v in versions]
    assert codes == ["AGILE-24-10-01"]          # only the current one covers 2026
    assert versions[0].available_to is None


def test_resolve_agile_versions_spans_multiple():
    versions = resolve_agile_versions(
        AgileListClient(), date(2024, 6, 1), date(2025, 1, 1))
    codes = [v.product_code for v in versions]
    assert codes == ["AGILE-23-12-06", "AGILE-24-10-01"]  # sorted by available_from


def test_resolve_agile_versions_override():
    versions = resolve_agile_versions(
        AgileListClient(), date(2026, 1, 1), date(2026, 5, 31), "AGILE-24-10-01")
    assert [v.product_code for v in versions] == ["AGILE-24-10-01"]


def test_resolve_agile_versions_none_raises():
    with pytest.raises(ValueError):
        resolve_agile_versions(AgileListClient(), date(2020, 1, 1), date(2020, 2, 1))
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_agile.py::test_resolve_agile_versions_filters_to_window -v`
Expected: FAIL with `ImportError: cannot import name 'resolve_agile_versions'`

- [ ] **Step 4: Implement**

Add to `src/octopus_compare/agile.py`:

```python
_AGILE_PREFIX = "AGILE-"


def _to_date(value: str | None) -> date | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(_UTC).date()


@dataclass
class AgileVersion:
    product_code: str
    display_name: str
    available_from: date
    available_to: date | None


def _version(code: str, d: dict) -> AgileVersion:
    return AgileVersion(
        product_code=code,
        display_name=d.get("full_name") or d.get("display_name") or code,
        available_from=_to_date(d.get("available_from")),
        available_to=_to_date(d.get("available_to")),
    )


def resolve_agile_versions(client, period_from, period_to, override=None):
    """Agile versions whose availability window intersects [period_from,
    period_to). Sourced from the public product list (Agile is listed). The
    override pins a single version."""
    if override:
        return [_version(override, client.get(f"products/{override}/"))]
    results = client.get_results("products/", {"brand": "OCTOPUS_ENERGY"})
    versions = [
        _version(r["code"], r)
        for r in results
        if r.get("code", "").startswith(_AGILE_PREFIX)
    ]
    in_window = [
        v for v in versions
        if v.available_from < period_to and (v.available_to or date.max) > period_from
    ]
    if not in_window:
        raise ValueError("No Octopus Agile product covering this window was found")
    return sorted(in_window, key=lambda v: v.available_from)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_agile.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/octopus_compare/agile.py tests/test_agile.py tests/fixtures/api_samples.py
git commit -m "feat: resolve Agile product versions for the window from the product list"
```

---

### Task 4: Agile resolvers (rate + standing charge)

**Files:**
- Modify: `src/octopus_compare/agile.py`
- Test: `tests/test_agile.py`

**Interfaces:**
- Consumes: `AgileVersion` (Task 3); `HalfHourlyRates` (Task 2); `fetch_standing_charges` + `VersionedLookup` from `rates.py`; `build_tariff_code` from `account.py`.
- Produces: `agile_resolvers(client, versions, region, period_from, period_to) -> tuple[Callable[[datetime], Decimal], Callable[[date], Decimal]]` — `(rate_for, sc_for)`: half-hourly unit rate by UTC instant (merged across versions, exc-VAT pence) and the daily standing charge by date (version-selected, exc-VAT pence).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_agile.py`:

```python
from octopus_compare.agile import agile_resolvers


class AgileRateClient:
    """Serves half-hourly Agile rates and a flat standing charge."""

    def get_results(self, path, params=None):
        if "standing-charges" in path:
            return [{"value_exc_vat": 45.0, "valid_from": None, "valid_to": None}]
        # standard-unit-rates: two aligned half-hours for 2026-03-01.
        return [
            {"value_exc_vat": 21.0, "valid_from": "2026-03-01T16:00:00Z",
             "valid_to": "2026-03-01T16:30:00Z"},
            {"value_exc_vat": -2.0, "valid_from": "2026-03-01T13:30:00Z",
             "valid_to": "2026-03-01T14:00:00Z"},
        ]


def test_agile_resolvers_single_version():
    v = AgileVersion("AGILE-24-10-01", "Agile Octopus", date(2024, 10, 1), None)
    rate_for, sc_for = agile_resolvers(
        AgileRateClient(), [v], "C", date(2026, 3, 1), date(2026, 3, 2))
    assert rate_for(datetime(2026, 3, 1, 16, 0, tzinfo=_UTC)) == Decimal("21.0")
    assert rate_for(datetime(2026, 3, 1, 13, 30, tzinfo=_UTC)) == Decimal("-2.0")
    assert sc_for(date(2026, 3, 1)) == Decimal("45.0")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_agile.py::test_agile_resolvers_single_version -v`
Expected: FAIL with `ImportError: cannot import name 'agile_resolvers'`

- [ ] **Step 3: Implement**

Add to `src/octopus_compare/agile.py` (add the two imports at the top of the file):

```python
from octopus_compare.account import build_tariff_code
from octopus_compare.rates import fetch_standing_charges, VersionedLookup
```

```python
def _iso(d: date) -> str:
    return d.strftime("%Y-%m-%dT00:00:00Z")


def agile_resolvers(client, versions, region, period_from, period_to):
    """(rate_for, sc_for) for the Agile column. Half-hourly unit rates from every
    version are merged into one instant-keyed lookup (version windows never
    overlap). Standing charges are daily and version-selected via VersionedLookup,
    mirroring tracker_resolvers."""
    by_instant: dict[datetime, Decimal] = {}
    sc_entries = []
    single = len(versions) == 1
    for v in versions:
        tariff = build_tariff_code("electricity", v.product_code, region)
        rate_results = client.get_results(
            f"products/{v.product_code}/electricity-tariffs/{tariff}/standard-unit-rates/",
            {"period_from": _iso(period_from), "period_to": _iso(period_to),
             "page_size": 25000},
        )
        for r in rate_results:
            by_instant[_utc_instant(r["valid_from"])] = Decimal(str(r["value_exc_vat"]))
        v_from, v_to = (date.min, None) if single else (v.available_from, v.available_to)
        sc_entries.append((
            v_from, v_to,
            fetch_standing_charges(client, "electricity", v.product_code, tariff,
                                   period_from, period_to),
        ))
    return HalfHourlyRates(by_instant).rate_for, VersionedLookup(sc_entries).rate_for
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_agile.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/octopus_compare/agile.py tests/test_agile.py
git commit -m "feat: assemble Agile half-hourly rate + daily standing-charge resolvers"
```

---

### Task 5: Half-hourly cost engine

**Files:**
- Create: `src/octopus_compare/agile_costing.py`
- Test: `tests/test_agile_costing.py`

**Interfaces:**
- Consumes: `SupplyCost`, `standing_pence` from `costing.py`; `pounds`, `round_pence`, `vat_pence` from `money.py`.
- Produces: `agile_supply_cost(halfhourly_kwh: dict[datetime, Decimal], rate_p_for: Callable[[datetime], Decimal], sc_p_for: Callable[[date], Decimal]) -> SupplyCost`. Energy is rounded once per London-local day; supports negative rates.

- [ ] **Step 1: Write the failing test**

Create `tests/test_agile_costing.py`:

```python
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from octopus_compare.agile_costing import agile_supply_cost

_UTC = ZoneInfo("UTC")


def _const(value):
    return lambda _key: Decimal(value)


def test_agile_supply_cost_basic():
    kwh = {
        datetime(2026, 3, 1, 0, 0, tzinfo=_UTC): Decimal("1.0"),
        datetime(2026, 3, 1, 0, 30, tzinfo=_UTC): Decimal("2.0"),
    }
    cost = agile_supply_cost(kwh, _const("20.0"), _const("45.0"))
    # energy = round(1*20 + 2*20) = 60p; standing = 45p (one day); subtotal 105p
    assert cost.energy_pounds == Decimal("0.60")
    assert cost.standing_pounds == Decimal("0.45")
    assert cost.vat_pounds == Decimal("0.05")        # round(105*0.05)=5p
    assert cost.total_pounds == Decimal("1.10")
    assert cost.consumption_kwh == Decimal("3.0")


def test_agile_supply_cost_handles_negative_rates():
    kwh = {datetime(2026, 3, 1, 13, 30, tzinfo=_UTC): Decimal("2.0")}

    def rate(_instant):
        return Decimal("-3.0")

    cost = agile_supply_cost(kwh, rate, _const("0.0"))
    # energy = round(2 * -3) = -6p -> a credit
    assert cost.energy_pounds == Decimal("-0.06")


def test_agile_supply_cost_rounds_per_day():
    # Two half-hours on different London days each round independently.
    kwh = {
        datetime(2026, 3, 1, 12, 0, tzinfo=_UTC): Decimal("0.333"),
        datetime(2026, 3, 2, 12, 0, tzinfo=_UTC): Decimal("0.333"),
    }
    cost = agile_supply_cost(kwh, _const("10.0"), _const("0.0"))
    # each day: round(0.333*10)=round(3.33)=3p -> 6p total
    assert cost.energy_pounds == Decimal("0.06")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_agile_costing.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'octopus_compare.agile_costing'`

- [ ] **Step 3: Implement**

Create `src/octopus_compare/agile_costing.py`:

```python
from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from octopus_compare.costing import SupplyCost, standing_pence
from octopus_compare.money import pounds, round_pence, vat_pence

_LONDON = ZoneInfo("Europe/London")


def _local_date(instant: datetime) -> date:
    return instant.astimezone(_LONDON).date()


def agile_energy_pence(
    halfhourly_kwh: dict[datetime, Decimal],
    rate_p_for: Callable[[datetime], Decimal],
) -> Decimal:
    """Sum over London-local days of round_half_up(sum of that day's
    half-hourly kwh × exc-VAT rate), in pence. One rounding per day, matching
    the daily engine; negative rates reduce the total."""
    by_day: dict[date, Decimal] = {}
    for instant, kwh in halfhourly_kwh.items():
        day = _local_date(instant)
        by_day[day] = by_day.get(day, Decimal(0)) + Decimal(kwh) * Decimal(rate_p_for(instant))
    return sum((round_pence(v) for v in by_day.values()), Decimal(0))


def agile_supply_cost(
    halfhourly_kwh: dict[datetime, Decimal],
    rate_p_for: Callable[[datetime], Decimal],
    sc_p_for: Callable[[date], Decimal],
) -> SupplyCost:
    days = sorted({_local_date(i) for i in halfhourly_kwh})
    energy_p = agile_energy_pence(halfhourly_kwh, rate_p_for)
    sc_p = standing_pence(days, sc_p_for)
    subtotal_p = energy_p + sc_p
    vat_p = vat_pence(subtotal_p)
    total_p = subtotal_p + vat_p
    consumption = sum((Decimal(v) for v in halfhourly_kwh.values()), Decimal(0))
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

Run: `python -m pytest tests/test_agile_costing.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/octopus_compare/agile_costing.py tests/test_agile_costing.py
git commit -m "feat: half-hourly Agile cost engine with per-day rounding"
```

---

### Task 6: Time-of-use insight

**Files:**
- Create: `src/octopus_compare/agile_insight.py`
- Test: `tests/test_agile_insight.py`

**Interfaces:**
- Consumes: `pounds` from `money.py`.
- Produces: `HalfHourStat(when: datetime, rate_p: Decimal, kwh: Decimal, cost_pounds: Decimal)`; `AgileInsight(...)` (fields below); `compute_insight(halfhourly_kwh: dict[datetime, Decimal], agile_rate_for: Callable[[datetime], Decimal], flex_rate_for: Callable[[date], Decimal], peak_window: tuple[time, time]) -> AgileInsight`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_agile_insight.py`:

```python
from datetime import date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

from octopus_compare.agile_insight import compute_insight

_UTC = ZoneInfo("UTC")
PEAK = (time(16, 0), time(19, 0))


def _agile_rate(instant):
    # 16:00 UTC slot is dear, the 00:00 slot is cheap (negative).
    return Decimal("30.0") if instant.hour == 16 else Decimal("-2.0")


def _flex_rate(_day):
    return Decimal("24.0")


def test_compute_insight_peak_and_effective_price():
    kwh = {
        datetime(2026, 3, 1, 0, 0, tzinfo=_UTC): Decimal("1.0"),    # off-peak, -2p
        datetime(2026, 3, 1, 16, 0, tzinfo=_UTC): Decimal("1.0"),   # peak (16:00 London), 30p
    }
    ins = compute_insight(kwh, _agile_rate, _flex_rate, PEAK)
    # agile energy = (1*-2 + 1*30) = 28p over 2 kWh -> 14.0 p/kWh
    assert ins.agile_effective_p == Decimal("14.0")
    assert ins.flex_effective_p == Decimal("24.0")
    assert ins.peak_pct == Decimal("50.0")
    assert ins.peak_kwh == Decimal("1.0")
    assert ins.negative_count == 1
    assert ins.cheapest.rate_p == Decimal("-2.0")
    assert ins.priciest.rate_p == Decimal("30.0")
    assert ins.priciest.when.hour == 16        # London local hour
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_agile_insight.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'octopus_compare.agile_insight'`

- [ ] **Step 3: Implement**

Create `src/octopus_compare/agile_insight.py`:

```python
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

from octopus_compare.money import pounds

_LONDON = ZoneInfo("Europe/London")


@dataclass
class HalfHourStat:
    when: datetime          # London local
    rate_p: Decimal         # exc-VAT pence/kWh
    kwh: Decimal
    cost_pounds: Decimal    # exc-VAT


@dataclass
class AgileInsight:
    agile_effective_p: Decimal      # exc-VAT pence/kWh
    flex_effective_p: Decimal
    peak_window: tuple
    peak_kwh: Decimal
    offpeak_kwh: Decimal
    peak_pct: Decimal
    peak_agile_pounds: Decimal      # exc-VAT
    peak_flex_pounds: Decimal
    cheapest: HalfHourStat
    priciest: HalfHourStat
    negative_count: int


def _effective_p(energy_p: Decimal, total_kwh: Decimal) -> Decimal:
    if total_kwh == 0:
        return Decimal(0)
    return (energy_p / total_kwh).quantize(Decimal("0.1"))


def compute_insight(
    halfhourly_kwh: dict[datetime, Decimal],
    agile_rate_for: Callable[[datetime], Decimal],
    flex_rate_for: Callable[[date], Decimal],
    peak_window: tuple,
) -> AgileInsight:
    start, end = peak_window
    total_kwh = agile_energy_p = flex_energy_p = Decimal(0)
    peak_kwh = peak_agile_p = peak_flex_p = Decimal(0)
    negative_count = 0
    cheapest = priciest = None
    for instant, kwh in halfhourly_kwh.items():
        local = instant.astimezone(_LONDON)
        a_rate = Decimal(agile_rate_for(instant))
        f_rate = Decimal(flex_rate_for(local.date()))
        a_cost = Decimal(kwh) * a_rate
        total_kwh += Decimal(kwh)
        agile_energy_p += a_cost
        flex_energy_p += Decimal(kwh) * f_rate
        if a_rate < 0:
            negative_count += 1
        if start <= local.time() < end:
            peak_kwh += Decimal(kwh)
            peak_agile_p += a_cost
            peak_flex_p += Decimal(kwh) * f_rate
        stat = HalfHourStat(local, a_rate, Decimal(kwh), pounds(a_cost))
        if cheapest is None or a_rate < cheapest.rate_p:
            cheapest = stat
        if priciest is None or a_rate > priciest.rate_p:
            priciest = stat
    peak_pct = (peak_kwh / total_kwh * 100).quantize(Decimal("0.1")) if total_kwh else Decimal(0)
    return AgileInsight(
        agile_effective_p=_effective_p(agile_energy_p, total_kwh),
        flex_effective_p=_effective_p(flex_energy_p, total_kwh),
        peak_window=peak_window,
        peak_kwh=peak_kwh,
        offpeak_kwh=total_kwh - peak_kwh,
        peak_pct=peak_pct,
        peak_agile_pounds=pounds(peak_agile_p),
        peak_flex_pounds=pounds(peak_flex_p),
        cheapest=cheapest,
        priciest=priciest,
        negative_count=negative_count,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_agile_insight.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/octopus_compare/agile_insight.py tests/test_agile_insight.py
git commit -m "feat: time-of-use insight (effective price, peak split, min/max half-hours)"
```

---

### Task 7: Agile report dataclasses + formatters

**Files:**
- Modify: `src/octopus_compare/report.py`
- Test: `tests/test_agile_report.py`

**Interfaces:**
- Consumes: `SupplyCost` (`costing.py`); `AgileInsight`, `HalfHourStat` (`agile_insight.py`); `AgileVersion` (`agile.py`); existing `_cheapest`, `_pct`, `_cell`, `_month_label` helpers in `report.py`.
- Produces: `AgileMonthlyRow(month, days, flexible_pounds, agile_pounds)` with `.cheapest`; `AgileResult(...)` with `.flexible_total`, `.agile_total`, `.cheapest`; `recommend_agile(result, threshold_pct=Decimal("2")) -> str` ("STAY"/"MARGINAL"/"SWITCH"); `format_agile_text(result) -> str`; `format_agile_json(result) -> str`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_agile_report.py`:

```python
import json
from datetime import date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

from octopus_compare.agile import AgileVersion
from octopus_compare.agile_insight import AgileInsight, HalfHourStat
from octopus_compare.costing import SupplyCost
from octopus_compare.report import (
    AgileResult, AgileMonthlyRow, recommend_agile,
    format_agile_text, format_agile_json)

_LONDON = ZoneInfo("Europe/London")


def _cost(total):
    t = Decimal(total)
    return SupplyCost(Decimal("100"), t, Decimal("0"), t, Decimal("0"), t)


def _insight():
    when = datetime(2026, 3, 1, 13, 30, tzinfo=_LONDON)
    stat = HalfHourStat(when, Decimal("-2.0"), Decimal("0.4"), Decimal("-0.01"))
    return AgileInsight(
        agile_effective_p=Decimal("18.4"), flex_effective_p=Decimal("24.5"),
        peak_window=(time(16, 0), time(19, 0)),
        peak_kwh=Decimal("250"), offpeak_kwh=Decimal("562"),
        peak_pct=Decimal("31.0"), peak_agile_pounds=Decimal("58.20"),
        peak_flex_pounds=Decimal("61.70"), cheapest=stat, priciest=stat,
        negative_count=37)


def _result(flex_total, agile_total):
    v = AgileVersion("AGILE-24-10-01", "Agile Octopus", date(2024, 10, 1), None)
    return AgileResult(
        period_from=date(2026, 1, 1), period_to=date(2026, 5, 31), region="C",
        agile_versions=[v],
        elec_flexible=_cost(flex_total), elec_agile=_cost(agile_total),
        monthly=[AgileMonthlyRow(date(2026, 1, 1), 31,
                                 Decimal(flex_total), Decimal(agile_total))],
        insight=_insight())


def test_recommend_agile_switch():
    assert recommend_agile(_result("286.80", "234.64")) == "SWITCH"


def test_recommend_agile_stay():
    assert recommend_agile(_result("234.64", "286.80")) == "STAY"


def test_format_agile_text_has_columns_and_insight():
    text = format_agile_text(_result("286.80", "234.64"))
    assert "Agile Comparison" in text and "(electricity only)" in text
    assert "AGILE-24-10-01" in text
    assert "Flexible" in text and "Agile" in text and "✓" in text
    assert "Time-of-use insight" in text
    assert "18.4p/kWh" in text
    assert "AGILE — £234.64" in text


def test_format_agile_json_shape():
    data = json.loads(format_agile_json(_result("286.80", "234.64")))
    assert data["cheapest"] == "agile"
    assert data["agile_total"] == "234.64"
    assert data["electricity"]["agile"]["total"] == "234.64"
    assert data["insight"]["agile_effective_p"] == "18.4"
    assert data["recommendation"] == "SWITCH"
    assert data["agile_versions"][0]["product_code"] == "AGILE-24-10-01"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_agile_report.py -v`
Expected: FAIL with `ImportError: cannot import name 'AgileResult'`

- [ ] **Step 3: Implement**

Add to `src/octopus_compare/report.py` (top-of-file import alongside the existing `from octopus_compare.tracker import ...`):

```python
from octopus_compare.agile_insight import AgileInsight
```

Append to `src/octopus_compare/report.py`:

```python
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

    @property
    def flexible_total(self) -> Decimal:
        return self.elec_flexible.total_pounds

    @property
    def agile_total(self) -> Decimal:
        return self.elec_agile.total_pounds

    @property
    def cheapest(self) -> str:
        return "flexible" if self.flexible_total <= self.agile_total else "agile"


def recommend_agile(result: AgileResult, threshold_pct: Decimal = Decimal("2")) -> str:
    if result.cheapest == "flexible":
        return "STAY"
    saving_pct = _pct(result.flexible_total - result.agile_total, result.flexible_total)
    return "MARGINAL" if saving_pct <= threshold_pct else "SWITCH"


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
        f"  consumption          {agile.consumption_kwh} kWh",
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


def _agile_reco_lines(result: AgileResult) -> list[str]:
    if result.cheapest == "flexible":
        return ["→ STAY on Flexible — cheapest over this period."]
    saving = result.flexible_total - result.agile_total
    pct = _pct(saving, result.flexible_total)
    if recommend_agile(result) == "MARGINAL":
        return [f"→ Cheapest over this period: AGILE — £{result.agile_total}, but only "
                f"{pct}% (£{saving}) under Flexible — MARGINAL, your call."]
    return [f"→ Cheapest over this period: AGILE — £{result.agile_total}, {pct}% "
            f"(£{saving}) less than Flexible."]


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
    c = result.cheapest
    lines.append(
        f"  {'Total':<20} "
        f"{_cell(result.flexible_total, c == 'flexible'):<14}"
        f"{_cell(result.agile_total, c == 'agile')}"
    )
    lines.append("")
    lines += _agile_insight_lines(result.insight)
    lines += _agile_reco_lines(result)
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


def format_agile_json(result: AgileResult) -> str:
    ins = result.insight
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
            "cheapest": result.cheapest,
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
            "recommendation": recommend_agile(result),
        },
        indent=2,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_agile_report.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/octopus_compare/report.py tests/test_agile_report.py
git commit -m "feat: Agile report dataclasses, text + JSON formatters, 2-way recommendation"
```

---

### Task 8: Agile pipeline (orchestration)

**Files:**
- Create: `src/octopus_compare/agile_pipeline.py`
- Test: `tests/test_agile_pipeline.py`

**Interfaces:**
- Consumes: `parse_account`, `region_letter`, `build_tariff_code` (`account.py`); `resolve_flexible` (`tracker.py`); `fetch_daily`, `fetch_halfhourly` (`consumption.py`); `fetch_rates`, `fetch_standing_charges` (`rates.py`); `supply_cost`, `month_slices` (`costing.py`); `resolve_agile_versions`, `agile_resolvers` (`agile.py`); `agile_supply_cost` (`agile_costing.py`); `compute_insight` (`agile_insight.py`); `AgileResult`, `AgileMonthlyRow` (`report.py`); `PricingError` (`pipeline.py`).
- Produces: `run_agile_comparison(client, config: Config) -> AgileResult`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_agile_pipeline.py`:

```python
from datetime import date, time
from decimal import Decimal

import pytest

from octopus_compare.config import Config
from octopus_compare.agile_pipeline import run_agile_comparison
from octopus_compare.pipeline import PricingError
from tests.fixtures.api_samples import ACCOUNT, AGILE_PRODUCTS_LIST


def _hh_rows(day, slots):
    # slots: list of (HH:MM, kwh)
    out = []
    for hhmm, kwh in slots:
        out.append({"consumption": kwh,
                    "interval_start": f"{day}T{hhmm}:00Z",
                    "interval_end": f"{day}T{hhmm}:00Z"})
    return out


def _rate_rows(day, slots):
    out = []
    for hhmm, value in slots:
        out.append({"value_exc_vat": value,
                    "valid_from": f"{day}T{hhmm}:00Z",
                    "valid_to": f"{day}T{hhmm}:00Z"})
    return out


HH = [("00:00", 1.0), ("16:00", 1.0)]           # 2 kWh on 2026-03-01
AGILE_RATES = [("00:00", -2.0), ("16:00", 30.0)]


class AgileFakeClient:
    """Flexible (VAR) flat at 24p/40p; Agile cheaper on average; one Agile
    version; half-hourly usage + rates for 2026-03-01."""

    def get(self, path, params=None):
        if path == "accounts/A-8F18337C/":
            return ACCOUNT
        if path == "products/VAR-22-11-01/":
            return {"is_tracker": False}
        raise AssertionError(path)

    def get_results(self, path, params=None):
        if path == "products/":
            return AGILE_PRODUCTS_LIST
        if "consumption" in path:
            if params and params.get("group_by") == "day":
                return _hh_rows("2026-03-01", HH)   # daily call: same total kWh
            return _hh_rows("2026-03-01", HH)
        if "standing-charges" in path:
            value = 40.0 if "VAR" in path else 45.0
            return [{"value_exc_vat": value, "valid_from": None, "valid_to": None}]
        if "AGILE" in path:                          # half-hourly unit rates
            return _rate_rows("2026-03-01", AGILE_RATES)
        return [{"value_exc_vat": 24.0, "valid_from": None, "valid_to": None}]  # VAR unit


def _config(**kw):
    base = dict(
        api_key="sk", account="A-8F18337C",
        period_from=date(2026, 3, 1), period_to=date(2026, 3, 2),
        output_format="text", gas_calorific_value=Decimal("39.5"),
        gas_units="kwh", verbose=False, command="agile",
        agile_product=None, peak_window=(time(16, 0), time(19, 0)))
    base.update(kw)
    return Config(**base)


def test_run_agile_comparison_basic():
    result = run_agile_comparison(AgileFakeClient(), _config())
    assert result.region == "C"
    assert result.agile_versions[0].product_code == "AGILE-24-10-01"
    # Agile (avg 14p/kWh) cheaper than Flexible (24p/kWh) on equal usage.
    assert result.agile_total < result.flexible_total
    assert result.cheapest == "agile"
    assert result.elec_agile.consumption_kwh == Decimal("2.0")
    # insight populated
    assert result.insight.negative_count == 1
    assert result.insight.priciest.rate_p == Decimal("30.0")


def test_run_agile_flexible_baseline_matches_daily_engine():
    # Flexible total here is computed by the unmodified daily supply_cost:
    # energy round(2 kWh × 24p)=48p + standing 40p = 88p subtotal;
    # VAT round(88 × 0.05)=round(4.4)=4p; total 92p -> £0.92.
    result = run_agile_comparison(AgileFakeClient(), _config())
    assert result.elec_flexible.total_pounds == Decimal("0.92")


class NoHalfHourlyClient(AgileFakeClient):
    def get_results(self, path, params=None):
        if "consumption" in path:
            return []
        return super().get_results(path, params)


def test_run_agile_no_halfhourly_data_raises():
    with pytest.raises(PricingError):
        run_agile_comparison(NoHalfHourlyClient(), _config())
```

Note on the fake: `fetch_daily` sends `group_by=day` and `fetch_halfhourly` does not; both return the same two rows here, so the daily Flexible baseline sees 2 kWh on 2026-03-01 (matching the half-hourly total). The daily engine buckets both rows under the same London day.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_agile_pipeline.py::test_run_agile_comparison_basic -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'octopus_compare.agile_pipeline'`

- [ ] **Step 3: Implement**

Create `src/octopus_compare/agile_pipeline.py`:

```python
from datetime import date
from decimal import Decimal
from zoneinfo import ZoneInfo

from octopus_compare.account import parse_account, region_letter, build_tariff_code
from octopus_compare.agile import resolve_agile_versions, agile_resolvers
from octopus_compare.agile_costing import agile_supply_cost
from octopus_compare.agile_insight import compute_insight
from octopus_compare.config import Config
from octopus_compare.consumption import fetch_daily, fetch_halfhourly
from octopus_compare.costing import supply_cost, month_slices
from octopus_compare.pipeline import PricingError
from octopus_compare.rates import fetch_rates, fetch_standing_charges
from octopus_compare.report import AgileResult, AgileMonthlyRow
from octopus_compare.tracker import resolve_flexible

_LONDON = ZoneInfo("Europe/London")


def _flex_resolvers(client, flex, region, cfg):
    tariff = build_tariff_code("electricity", flex.product_code, region)
    rates = fetch_rates(client, "electricity", flex.product_code, tariff,
                        cfg.period_from, cfg.period_to)
    sc = fetch_standing_charges(client, "electricity", flex.product_code, tariff,
                                cfg.period_from, cfg.period_to)
    return rates.rate_for, sc.rate_for


def _halfhourly_months(hh):
    """{first_of_month(local): {instant: kwh}}."""
    buckets: dict[date, dict] = {}
    for instant, kwh in hh.items():
        month = instant.astimezone(_LONDON).date().replace(day=1)
        buckets.setdefault(month, {})[instant] = kwh
    return buckets


def run_agile_comparison(client, config: Config) -> AgileResult:
    info = parse_account(client.get(f"accounts/{config.account}/"))
    meter = info.electricity
    flex = resolve_flexible(client, meter)
    region = config.region or region_letter(flex.tariff_code)

    daily = fetch_daily(client, "electricity", meter.identifier, meter.serials,
                        config.period_from, config.period_to)
    hh = fetch_halfhourly(client, meter.identifier, meter.serials,
                          config.period_from, config.period_to)
    if not hh:
        raise PricingError(
            "No half-hourly electricity data for this period — the Agile comparison "
            "needs half-hourly smart-meter readings. Try a different window with "
            "--from/--to, or check your meter is in half-hourly mode."
        )

    flex_rate_for, flex_sc_for = _flex_resolvers(client, flex, region, config)
    versions = resolve_agile_versions(client, config.period_from, config.period_to,
                                      config.agile_product)
    agile_rate_for, agile_sc_for = agile_resolvers(
        client, versions, region, config.period_from, config.period_to)

    try:
        elec_flex = supply_cost(daily, flex_rate_for, flex_sc_for)
        elec_agile = agile_supply_cost(hh, agile_rate_for, agile_sc_for)
        flex_months = {m: sub for m, sub in month_slices(daily)}
        agile_months = _halfhourly_months(hh)
        monthly = []
        for month in sorted(set(flex_months) | set(agile_months)):
            f_slice = flex_months.get(month, {})
            a_slice = agile_months.get(month, {})
            days = len(set(f_slice) | {i.astimezone(_LONDON).date() for i in a_slice})
            f_cost = supply_cost(f_slice, flex_rate_for, flex_sc_for) if f_slice else None
            a_cost = agile_supply_cost(a_slice, agile_rate_for, agile_sc_for) if a_slice else None
            monthly.append(AgileMonthlyRow(
                month=month, days=days,
                flexible_pounds=f_cost.total_pounds if f_cost else Decimal(0),
                agile_pounds=a_cost.total_pounds if a_cost else Decimal(0)))
    except KeyError as e:
        raise PricingError(
            f"Couldn't price every half-hour on Agile: {e}. Rates don't cover the "
            "full period — try a narrower window with --from/--to."
        ) from e

    insight = compute_insight(hh, agile_rate_for, flex_rate_for, config.peak_window)

    return AgileResult(
        period_from=config.period_from, period_to=config.period_to, region=region,
        agile_versions=versions,
        elec_flexible=elec_flex, elec_agile=elec_agile,
        monthly=monthly, insight=insight,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_agile_pipeline.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/octopus_compare/agile_pipeline.py tests/test_agile_pipeline.py
git commit -m "feat: Agile pipeline — daily Flexible baseline + half-hourly Agile + insight"
```

---

### Task 9: CLI subcommand + routing

**Files:**
- Modify: `src/octopus_compare/config.py`
- Modify: `src/octopus_compare/cli.py`
- Modify: `README.md`
- Test: `tests/test_config.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: `run_agile_comparison` (`agile_pipeline.py`); `format_agile_text`, `format_agile_json` (`report.py`).
- Produces: `Config` gains `command: str = "compare"`, `agile_product: str | None = None`, `peak_window: tuple = (time(16, 0), time(19, 0))`. `load_config` accepts an optional `agile` subcommand; no subcommand → `command="compare"`. `cli.main` routes on `cfg.command`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_config.py`:

```python
from datetime import time


def test_no_subcommand_defaults_to_compare():
    cfg = load_config([], ENV, TODAY)
    assert cfg.command == "compare"
    assert cfg.agile_product is None
    assert cfg.peak_window == (time(16, 0), time(19, 0))


def test_agile_subcommand():
    cfg = load_config(["agile"], ENV, TODAY)
    assert cfg.command == "agile"


def test_agile_subcommand_shares_common_flags():
    cfg = load_config(["agile", "--from", "2026-01-01", "--to", "2026-05-31"],
                      ENV, TODAY)
    assert cfg.command == "agile"
    assert cfg.period_from == date(2026, 1, 1)
    assert cfg.period_to == date(2026, 5, 31)


def test_agile_product_and_peak_window_flags():
    cfg = load_config(
        ["agile", "--agile-product", "AGILE-24-10-01", "--peak-window", "17:00-20:00"],
        ENV, TODAY)
    assert cfg.agile_product == "AGILE-24-10-01"
    assert cfg.peak_window == (time(17, 0), time(20, 0))


def test_compare_flags_still_work_without_subcommand():
    cfg = load_config(["--tracker-product", "SILVER-26-04-01"], ENV, TODAY)
    assert cfg.command == "compare"
    assert cfg.tracker_product == "SILVER-26-04-01"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_config.py::test_agile_subcommand -v`
Expected: FAIL with `TypeError`/`AttributeError` (no `command` field / unknown subcommand)

- [ ] **Step 3: Implement config**

Replace the `Config` dataclass and `load_config` in `src/octopus_compare/config.py`. Update the imports line to `from datetime import date, datetime, time, timedelta`, then:

```python
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
    tracker_product: str | None = None
    region: str | None = None
    fixed_product: str | None = None
    command: str = "compare"
    agile_product: str | None = None
    peak_window: tuple = (time(16, 0), time(19, 0))


def _parse_time(value: str) -> time:
    return datetime.strptime(value.strip(), "%H:%M").time()


def _parse_peak_window(value: str) -> tuple:
    start, end = value.split("-")
    return (_parse_time(start), _parse_time(end))


def load_config(argv: list[str], env: dict[str, str], today: date) -> Config:
    parser = argparse.ArgumentParser(prog="octopus-compare")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--months", type=int, default=3)
    common.add_argument("--from", dest="from_", type=_parse_date)
    common.add_argument("--to", dest="to", type=_parse_date)
    common.add_argument("--format", choices=["text", "json"], default="text")
    common.add_argument("--gas-calorific-value", type=Decimal, default=Decimal("39.5"))
    common.add_argument("--gas-units", choices=["auto", "m3", "kwh"], default="auto")
    common.add_argument("--verbose", action="store_true")
    common.add_argument("--tracker-product", dest="tracker_product", default=None)
    common.add_argument("--region", dest="region", default=None)
    common.add_argument("--fixed-product", dest="fixed_product", default=None)

    sub = parser.add_subparsers(dest="command")
    sub.add_parser("compare", parents=[common])
    agile_p = sub.add_parser("agile", parents=[common])
    agile_p.add_argument("--agile-product", dest="agile_product", default=None)
    agile_p.add_argument("--peak-window", dest="peak_window",
                         type=_parse_peak_window, default=(time(16, 0), time(19, 0)))

    # No subcommand → behave as 'compare' with the common flags.
    if argv and argv[0] in ("compare", "agile"):
        args = parser.parse_args(argv)
    else:
        args = parser.parse_args(["compare", *argv])

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
        tracker_product=args.tracker_product,
        region=args.region,
        fixed_product=args.fixed_product,
        command=args.command or "compare",
        agile_product=getattr(args, "agile_product", None),
        peak_window=getattr(args, "peak_window", (time(16, 0), time(19, 0))),
    )
```

- [ ] **Step 4: Run config tests to verify they pass**

Run: `python -m pytest tests/test_config.py -v`
Expected: PASS (new and existing)

- [ ] **Step 5: Write the failing CLI routing test**

Add to `tests/test_cli.py`:

```python
def test_main_routes_to_agile(monkeypatch, capsys):
    import octopus_compare.cli as cli

    class FakeResult:
        pass

    monkeypatch.setattr(cli, "_load_env",
                        lambda: {"OCTOPUS_API_KEY": "sk", "OCTOPUS_ACCOUNT": "A-1"})
    monkeypatch.setattr(cli, "_build_client", lambda cfg: object())
    called = {}
    monkeypatch.setattr(cli, "run_agile_comparison",
                        lambda client, cfg: called.setdefault("agile", True) or FakeResult())
    monkeypatch.setattr(cli, "format_agile_text", lambda result: "AGILE-OUTPUT")

    rc = cli.main(["agile"])
    assert rc == 0
    assert called.get("agile") is True
    assert "AGILE-OUTPUT" in capsys.readouterr().out
```

(Match the monkeypatch style already used in `tests/test_cli.py`; if that file stubs differently, follow its existing pattern for `_load_env`/`_build_client`.)

- [ ] **Step 6: Run it to verify it fails**

Run: `python -m pytest tests/test_cli.py::test_main_routes_to_agile -v`
Expected: FAIL with `AttributeError: ... has no attribute 'run_agile_comparison'`

- [ ] **Step 7: Implement CLI routing**

In `src/octopus_compare/cli.py`, add imports near the existing ones:

```python
from octopus_compare.agile_pipeline import run_agile_comparison
from octopus_compare.report import format_text, format_json, format_agile_text, format_agile_json
```

Replace the output-building block in `main()` (the `try:` that calls `run_comparison` and the later `output = ...` line) with a branch on `cfg.command`:

```python
    try:
        client = _build_client(cfg)
        if cfg.command == "agile":
            result = run_agile_comparison(client, cfg)
        else:
            result = run_comparison(client, cfg)
    except ApiError as e:
        print(f"Octopus API error: {e}", file=sys.stderr)
        return 3
    except (PricingError, ValueError) as e:
        print(str(e), file=sys.stderr)
        return 3

    if cfg.verbose:
        print(
            f"period {cfg.period_from} to {cfg.period_to} | "
            f"gas_units={cfg.gas_units} calorific_value={cfg.gas_calorific_value}",
            file=sys.stderr,
        )

    if cfg.command == "agile":
        output = format_agile_json(result) if cfg.output_format == "json" else format_agile_text(result)
    else:
        output = format_json(result) if cfg.output_format == "json" else format_text(result)
    print(output)
    return 0
```

- [ ] **Step 8: Update the README**

In `README.md`, under `## Usage`, add:

```
    octopus-compare agile                 # Flexible vs Agile (electricity only), half-hourly backtest
    octopus-compare agile --from 2026-01-01 --to 2026-05-31
    octopus-compare agile --agile-product AGILE-24-10-01   # pin a specific Agile version
    octopus-compare agile --peak-window 17:00-20:00        # redefine the peak band (default 16:00-19:00)
```

And add a short paragraph: the `agile` subcommand costs your real half-hourly electricity usage against Agile's published half-hourly rates for the same dates (a pure what-if backtest), reports Flexible-vs-Agile totals and a monthly table, and a time-of-use insight block (effective p/kWh, peak share, cheapest/priciest half-hours, negative-price slots). Gas is excluded — Agile is electricity-only.

- [ ] **Step 9: Run the full suite**

Run: `python -m pytest`
Expected: PASS (all tests, including the unchanged daily-report and penny-exact bill evals)

- [ ] **Step 10: Commit**

```bash
git add src/octopus_compare/config.py src/octopus_compare/cli.py README.md tests/test_config.py tests/test_cli.py
git commit -m "feat: octopus-compare agile subcommand + routing; README"
```

---

### Task 10: Live-eval smoke check (optional)

**Files:**
- Modify: `tests/test_live_eval.py`

**Interfaces:**
- Consumes: `run_agile_comparison`, `Config` — same live-eval harness the file already uses.

- [ ] **Step 1: Add a guarded smoke test**

Add to `tests/test_live_eval.py`, mirroring the existing `OCTOPUS_LIVE_EVAL` gate and client construction used in that file:

```python
def test_live_agile_smoke():
    if not os.environ.get("OCTOPUS_LIVE_EVAL"):
        pytest.skip("set OCTOPUS_LIVE_EVAL=1 to run live")
    # Build the real client + Config(command="agile") exactly as the other live
    # tests in this file do, over a recent ~1-month window, then:
    result = run_agile_comparison(client, cfg)
    assert result.elec_agile.consumption_kwh > 0
    assert result.elec_agile.total_pounds > 0
    assert result.agile_versions
    assert result.insight.cheapest.rate_p <= result.insight.priciest.rate_p
```

(Follow the existing file's exact pattern for building `client` and `cfg`; reuse its env/account plumbing rather than duplicating credential handling.)

- [ ] **Step 2: Verify it skips offline**

Run: `python -m pytest tests/test_live_eval.py::test_live_agile_smoke -v`
Expected: SKIPPED (no `OCTOPUS_LIVE_EVAL`)

- [ ] **Step 3: Commit**

```bash
git add tests/test_live_eval.py
git commit -m "test: optional live smoke check for the agile subcommand"
```

---

## Self-Review

**Spec coverage:**
- §2 separate subcommand → Task 9. Electricity-only → enforced throughout (Tasks 1, 4, 8). Historical backtest (date-versioned rates) → Tasks 3–4. Totals + monthly + insight → Tasks 7, 8, 6. Engine isolation / Flexible baseline reuse → Task 8 (`supply_cost` on daily) + consistency test. No volatility caveat → Task 7 reco lines.
- §3 grounding facts → Task 3 (AGILE- prefix, window intersection), Task 4 (region tariff code, half-hourly rates, daily standing charge).
- §4 output → Task 7 (header, two-column block, monthly ✓, insight, reco, disclaimer; JSON).
- §5 resolution + UTC-instant alignment → Tasks 2, 3, 4 (+ DST alignment test in Task 2).
- §6 per-day rounding + negative prices + insight fields → Tasks 5, 6.
- §7 module/data-model changes → every task; CLI restructure Task 9.
- §8 testing (negative slot, DST day, consistency, CLI, report) → Tasks 1–9.
- §9 edge cases: no HH data → Task 8; bad product/uncovered window → Tasks 3, 8; negative prices → Tasks 5, 6; DST → Task 2; monthly tie → Task 7 (`<=` favours Flexible).
- §10 out of scope: gas / outgoing / forward estimate / drill-down / column-in-daily-report — none implemented. ✓

**Placeholder scan:** No TBD/TODO; every code step has complete code. The two "follow the existing pattern" notes (Task 9 CLI test, Task 10 live eval) point at concrete existing files and are clearly marked — Task 10 is optional and gated.

**Type consistency:** `fetch_halfhourly` returns `dict[datetime, Decimal]` (UTC instants) consumed identically by `agile_resolvers.rate_for`, `agile_supply_cost`, and `compute_insight`. `agile_rate_for: (datetime)->Decimal` and `flex_rate_for: (date)->Decimal` are used with matching key types in Tasks 6 and 8. `AgileResult`/`AgileMonthlyRow` fields produced in Task 8 match those defined in Task 7. `peak_window: tuple[time, time]` flows from Task 9 config → Task 8 → Task 6 → Task 7 formatting consistently. `recommend_agile` returns `"STAY"|"MARGINAL"|"SWITCH"` as used in Task 7 and the JSON.
