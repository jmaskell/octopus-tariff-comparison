# A Separate Comparison: Flexible vs Agile — Design

**Date:** 2026-06-26
**Status:** Approved (design); pending implementation plan
**Builds on:** `2026-06-25-add-12m-fixed-comparison-design.md` (the three-column daily report)

## 1. Purpose

`octopus-compare` today costs real usage against **Flexible / Tracker / 12M Fixed**
at **daily** granularity — every one of those tariffs has a single unit rate per
day, so daily consumption × a daily rate is exact.

**Agile is fundamentally different:** its unit rate changes **every half hour** and
can go **negative** during plunge pricing. Answering "what would I have spent on
Agile?" therefore needs a separate data path — **half-hourly consumption ×
half-hourly rates** — which the daily engine cannot do.

This adds a **separate `agile` subcommand** that backtests the user's real
half-hourly usage against Agile's actual published half-hourly rates, alongside the
Flexible baseline, with a time-of-use insight block.

## 2. Decisions (from brainstorming)

- **Surfacing — separate subcommand.** `octopus-compare agile` runs only the
  Flexible-vs-Agile comparison; `octopus-compare` (no subcommand) is the existing
  3-column daily report, **unchanged**. Keeps the heavier half-hourly fetch
  (~4,000+ intervals over 3 months vs ~90 daily points) off the default run.
- **Scope — electricity only.** Agile is an electricity-only tariff (no gas Agile
  product), so this comparison is electricity only. Gas is excluded entirely.
- **Pricing model — historical backtest.** The user's *actual* half-hourly usage on
  each past date × the Agile half-hourly rates *actually published for that same
  date*. Answers "over this window, Agile would genuinely have cost me £X." Needs
  date-versioned Agile rates, chained across the window like Tracker.
- **Output — totals + monthly + insight.** Flexible-vs-Agile component totals, a
  per-month table (cheapest marked), and a time-of-use insight block (effective
  p/kWh, peak vs off-peak, cheapest/priciest half-hours, negative-price slots).
- **Engine isolation (approach C).** The penny-validated daily engine is **left
  untouched**. A new isolated half-hourly path reuses the value primitives
  (`SupplyCost`, `money.py`, the `VersionedLookup` concept). The **Flexible
  baseline reuses the existing daily `supply_cost`**, so its total is identical to
  the main report's Flexible total to the penny.
- **No volatility caveat.** The user understands the tariff; the recommendation
  states the result plainly. Only the existing "API-derived estimates incl. VAT"
  data-fidelity disclaimer is kept.

## 3. Grounding facts (to verify against the live public API at implementation)

- Agile products **are listed** (like Fixed, unlike Tracker):
  `GET /v1/products/?brand=OCTOPUS_ENERGY` returns versions with the code prefix
  `AGILE-` (e.g. `AGILE-24-10-01`, plus older `AGILE-*` and `AGILE-FLEX-*`
  versions). `is_variable: true`. The current version has `available_to: null`.
- Region is the trailing letter of the tariff code, e.g.
  `E-1R-AGILE-24-10-01-C`, built via the existing `build_tariff_code`.
- An Agile version publishes **half-hourly** unit rates over its availability
  window from `products/{code}/electricity-tariffs/{tariff}/standard-unit-rates/`
  with `period_from`/`period_to`; results are 30-minute windows with
  `valid_from`/`valid_to`, and `value_exc_vat` may be **negative**.
- The **standing charge is daily** even on Agile (one value per day from
  `standing-charges/`).
- Half-hourly **consumption** comes from the existing `consumption/` endpoint
  **without** `group_by=day`.

## 4. Output specification

```
Octopus Agile Comparison · 1 Jan – 31 May 2026 (151 days) · Region C  (electricity only)
Your real half-hourly usage costed against Agile's published half-hourly rates — a pure what-if backtest.
  Agile versions used: AGILE-24-10-01 "Agile Octopus" (+ earlier versions across the window)

Electricity              Flexible      Agile
  consumption            812.4 kWh     812.4 kWh
  energy (excl VAT)        £199.04       £149.37
  standing charge           £74.10        £74.10
  VAT (5%)                  £13.66        £11.17
  ─────────────────────────────────────────────
  total                    £286.80       £234.64

By month                 Flexible      Agile
  Jan 2026                  £64.20       £51.10 ✓
  Feb 2026                  £58.90 ✓     £62.30
  Mar 2026                  ...          ...
  ─────────────────────────────────────────────
  Total                    £286.80      £234.64 ✓

Time-of-use insight
  Effective unit price     24.5p/kWh     18.4p/kWh
  Peak (16:00–19:00)       31% of usage · Agile spend £58.20 (Flexible £61.70)
  Cheapest ½-hour          2026-03-14 13:30  −2.1p/kWh  (0.42 kWh, −£0.01)
  Priciest ½-hour          2026-01-09 17:30  78.4p/kWh  (0.91 kWh, £0.71)
  Negative-price slots     37 half-hours you'd have been paid to use

→ Cheapest over this period: AGILE — £234.64, 18.2% (£52.16) less than Flexible.
Figures are API-derived estimates incl. VAT, not your exact bill.
```

Rules:

- **Header:** period, region, an explicit `(electricity only)` marker, and a line
  naming the Agile version(s) used across the window.
- **Component block (Electricity only):** two columns — Flexible vs Agile —
  consumption / energy / standing / VAT / total.
- **Monthly table:** two absolute columns; the cheaper of the two per row marked
  with a trailing `✓` (and on the Total row). Tie → mark Flexible first (documented
  tie-break, consistent with the daily report).
- **Time-of-use insight block** (see §6).
- **Recommendation:** reuses the existing `_cheapest`/`recommend` two ways —
  Flexible cheapest → `STAY on Flexible`; Agile cheapest → `Cheapest over this
  period: AGILE — £{agile}, {pct}% (£{saving}) less than Flexible`, `MARGINAL` when
  `pct ≤ 2%`. No volatility caveat.
- **`--format json`** mirrors the existing JSON shape: `electricity.flexible` /
  `electricity.agile` component figures, an `agile` meta object (versions used),
  per-month `flexible`/`agile`/`cheapest`, totals, the `insight` block, and
  `recommendation`.

## 5. Agile resolution + half-hourly mechanics

**Resolve Agile versions** (`resolve_agile_versions`, new `agile.py`):
- `GET /v1/products/?brand=OCTOPUS_ENERGY`; keep results whose `code` starts with
  `AGILE-`. For each, read `available_from`/`available_to` (from the listing, or a
  detail fetch). Keep versions whose availability window **intersects** the
  `[period_from, period_to)` window. Mirrors `tracker_versions_for_window`, but
  sourced from the **public product list** (Agile is listed) rather than agreement
  history.
- `--agile-product CODE` short-circuits to a single pinned version (mirrors
  `--tracker-product`).
- Clear error if none resolvable.

**Half-hourly rate lookup** (new, datetime-keyed — the existing `RateLookup`
truncates to date and cannot serve Agile):
- For each version, fetch its half-hourly unit rates over the overlapping
  sub-window and build a lookup keyed by the half-hour's **absolute UTC instant**.
- Across versions, select the right version per day via the existing
  `VersionedLookup` concept, then delegate to that version's half-hourly lookup.
- **Standing charge** is daily → reuse the existing `fetch_standing_charges` +
  `VersionedLookup` unchanged.

**Alignment:** consumption half-hours are matched to Agile rate half-hours by their
**absolute UTC instant**, which avoids DST-transition ambiguity on the 46-/50-slot
days. Peak/off-peak classification uses **London local time**.

## 6. The half-hourly cost engine + insight

**Cost** (`agile_costing.py`, reusing `SupplyCost` + `money.py`):
- **Energy:** per half-hour `kwh × rate` at full `Decimal` precision (negative
  rates reduce the bill naturally); sum the full-precision products **per day**,
  `round_pence` once per day (matching the daily engine's one-rounding-per-day
  convention), then sum the days.
- **Standing charge:** existing `standing_pence` over the window's days via the
  versioned daily SC lookup.
- **VAT:** existing 5% `vat_pence` on the subtotal.
- **Fidelity note:** the user is not on Agile, so there is no real bill to validate
  to the penny against (unlike the daily engine's three bill fixtures). The per-day
  rounding convention of the validated engine is adopted deliberately as the most
  defensible choice; documented in code.

**Flexible baseline:** computed by the **existing daily `supply_cost`** on daily
electricity consumption — not a half-hourly recomputation. Flexible is flat, so the
total is mathematically identical, and reusing the daily path guarantees the
Flexible figure matches the main report to the penny. The agile pipeline therefore
fetches **both** daily consumption (Flexible baseline) and half-hourly consumption
(Agile + insight).

**Insight** (`AgileInsight` dataclass, computed in the agile pipeline):
- **Effective unit price:** total energy cost (exc VAT) ÷ total kWh, in p/kWh, for
  both Agile and Flexible.
- **Peak vs off-peak:** each half-hour classified by London local time against
  `--peak-window` (default `16:00-19:00`); reports kWh and Agile spend in-peak vs
  off-peak and the peak share of usage.
- **Cheapest / priciest half-hour:** the min- and max-rate half-hours actually
  consumed in (date/time, rate, kWh, cost), plus a **count of negative-price
  half-hours**.

## 7. Data model & module changes

- **`config.py` / `cli.py`** — argparse gains an **optional subcommand** via parent
  parsers: shared flags (`--from`, `--to`, `--months`, `--region`, `--format`,
  `--verbose`) on both; the `agile` subcommand adds `--agile-product CODE` and
  `--peak-window HH:MM-HH:MM` (default `16:00-19:00`). `Config` gains
  `command: "compare" | "agile"`, `agile_product`, `peak_window`. No subcommand →
  `command="compare"` (backward compatible). `main()` branches on `command`.
- **`consumption.py`** — add `fetch_halfhourly(...) -> dict[datetime, Decimal]`
  (no `group_by`, summed across serials, keyed by interval_start).
- **`agile.py`** (new) — `resolve_agile_versions`, the datetime-keyed half-hourly
  lookup, and `agile_resolvers` (half-hourly rate resolver + daily SC resolver).
- **`agile_costing.py`** (new) — the half-hourly `SupplyCost` cost function.
- **`agile_pipeline.py`** (new) — `run_agile_comparison`: resolve Flexible + region,
  fetch daily (baseline) and half-hourly consumption, resolve Agile versions, price
  Agile, compute the `AgileInsight`, assemble an `AgileResult`. KeyError →
  `PricingError` guard as in the daily pipeline.
- **`report.py`** — `format_agile_text` / `format_agile_json` reusing
  `_cheapest`/`recommend`/`_cell` and the money helpers; new `AgileResult`,
  `AgileMonthlyRow`, `AgileInsight` dataclasses (here or in the agile pipeline
  module).

## 8. Testing & evaluation

- **Fixtures** (`tests/fixtures/api_samples.py`) — half-hour consumption readings
  and matching Agile rate windows, including a **negative-price** slot and a
  **DST-transition** day (46-/50-slot) to exercise UTC-instant alignment.
- **`test_agile.py`** — version resolution from the product list (window
  intersection; `--agile-product` pin; error when none); datetime-keyed lookup
  picks the right half-hour and the right version across the chain.
- **agile cost engine** — per-day rounding, negative-price half-hours reduce the
  total, standing charge + VAT correct.
- **insight** — peak/off-peak classification by London local time, effective
  p/kWh, min/max half-hour selection, negative-slot count.
- **Consistency test** — the Flexible baseline total from the agile path **equals**
  the daily report's Flexible electricity total on the same fixture (the key
  guarantee of approach C).
- **CLI** — `octopus-compare agile` parses/routes; the no-subcommand path still
  produces the unchanged 3-column report; shared flags apply to both.
- **report** — text contains the two columns, the `✓` cheapest marker, the insight
  block; JSON carries component figures, agile meta, monthly rows, insight, totals,
  recommendation.
- **Existing tests** — untouched and green; the penny-exact daily evals are not
  modified.
- **Live eval** (`OCTOPUS_LIVE_EVAL=1`) — optional agile smoke check.

## 9. Edge cases & error handling

- **No half-hourly consumption available** (meter not in HH mode / no data) →
  clear, friendly message rather than a crash or a misleading zero.
- **No Agile product resolvable** / bad `--agile-product` (404) → clear error
  naming the code.
- **Agile rates don't cover the full window** → the same friendly `PricingError`
  ("rates don't cover the full period — try a narrower window with `--from/--to`").
- **Negative half-hour prices** → handled by `Decimal`; reduce the bill correctly
  and surface in the insight block.
- **DST transition days** → UTC-instant alignment handles the 46-/50-slot days.
- **Monthly tie** → mark Flexible first (documented).

## 10. Out of scope (YAGNI)

- Gas (no Agile gas product).
- Agile **Outgoing** / export.
- A forward "today's prices applied to past usage" estimate (rejected in favour of
  the historical backtest).
- Load-shifting / "what if you moved usage" what-ifs beyond the peak-share insight.
- A full half-hourly drill-down dump (insight summarises instead).
- Integrating Agile as a column in the daily 3-column report (it is a separate
  subcommand by decision).

## 11. Success criteria

- `octopus-compare agile` prints a Flexible-vs-Agile electricity comparison:
  component totals, a per-month table with the cheaper marked, a time-of-use
  insight block, and a STAY/MARGINAL/SWITCH recommendation framed against Flexible.
- Agile costs use the **historical backtest** — real half-hourly usage × the Agile
  rates published for those same dates, across all versions intersecting the window.
- The Flexible baseline matches the main report's Flexible electricity total to the
  penny.
- `octopus-compare` (no subcommand) and the penny-exact daily evals are unchanged
  and green; the daily engine is untouched.
- Negative prices, DST-transition days, and missing half-hourly data are handled
  gracefully.
