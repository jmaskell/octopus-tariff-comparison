# Octopus Tariff Comparison CLI — Design

**Date:** 2026-06-25
**Status:** Approved (design); pending implementation plan

## 1. Purpose

A command-line tool that uses the Octopus Energy API to answer one question:
**"Should we switch back to the Tracker tariff?"**

It compares what we actually pay on our current **Flexible Octopus** tariff against
what we *would have paid* on **Octopus Tracker** over a recent period, for both
electricity and gas, and prints a clear recommendation.

The owner's household (account `A-8F18337C`, London) was on Tracker until
24 March 2026, then dropped to Flexible. This tool quantifies the cost of that
decision and tells us whether to switch back.

## 2. Scope

**In scope**
- Electricity **and** gas, combined into a single total.
- Historical comparison: apply real Tracker daily rates to our real consumption
  and compare to what we actually paid on Flexible.
- A configurable comparison window (default: last 3 months).
- A plain-text terminal report with a switch recommendation.

**Out of scope (YAGNI)**
- Forward-looking price projection (Tracker changes daily; speculative).
- Web UI, database, scheduling, notifications.
- Tariffs other than the household's actual Flexible tariff and current Tracker.
- Penny-exact reconciliation to the bill including credits/adjustments — figures
  are API-derived estimates (typically within a percent or two of the bill).

## 3. Approach (decided)

**Approach A — REST API, cost computed from consumption × rates.**

From an API key + account number, the tool auto-discovers meters, the household's
actual Flexible tariff, and consumption. It computes cost two ways over the same
period using the **same consumption series**, so the only variable is price:

- **Actual (Flexible):** consumption × real Flexible unit rates + standing charge.
- **Hypothetical (Tracker):** *same* consumption × Tracker's actual daily rates +
  Tracker standing charge.

Rejected alternatives: GraphQL/Kraken for penny-exact billed amounts (much more
complex auth/queries, and doesn't improve the always-hypothetical Tracker side);
coarse totals × average rates (throws away the daily granularity that makes a
Tracker comparison meaningful).

## 4. Architecture

A small Python package run as a CLI. Single synchronous program; no server, no
database. Reads credentials from `.env`, calls the Octopus REST API, runs the
cost engine in memory, prints a report.

```
octopus/
  .env.example            # OCTOPUS_API_KEY=, OCTOPUS_ACCOUNT=
  .gitignore              # ignores .env, __pycache__, etc.
  pyproject.toml          # deps + console-script entry point (octopus-compare)
  README.md
  src/octopus_compare/
    __init__.py
    cli.py                # arg parsing + orchestration (entry point)
    config.py             # load .env + CLI args
    client.py             # Octopus REST client: auth, pagination, retry
    account.py            # discover meters, agreements, region, Flexible tariff
    tracker.py            # resolve current live Tracker product + tariff codes
    rates.py              # fetch unit rates + standing charges (with date windows)
    costing.py            # cost engine (the core; pure functions)
    report.py             # format output + recommendation
  tests/
    fixtures/bills.py     # transcribed ground-truth from the 3 PDF bills
    test_costing.py       # penny-exact + tolerance evals against bills
    test_account.py       # account/agreement parsing from sample JSON
    test_rates.py         # rate/standing-charge date-window matching
  bills/                  # the 3 source PDF bills (provided, used to build evals)
```

Dependencies kept minimal: `requests`, `python-dotenv`, `rich` (table output).
Testing with `pytest`.

## 5. Data model (core types)

- `Interval` — a consumption record: `start`, `end`, `kwh` (electricity already
  kWh; gas converted from m³, see §7).
- `Rate` — `valid_from`, `valid_to` (nullable = open-ended), `value_inc_vat`
  (p/kWh). Tracker has one per day; Flexible typically one flat rate per cap period.
- `StandingCharge` — `valid_from`, `valid_to`, `value_inc_vat` (p/day).
- `TariffRates` — the unit rates + standing charges for one supply on one tariff.
- `SupplyCost` — `consumption_kwh`, `energy_cost`, `standing_cost`, `total`,
  broken out for both Flexible (actual) and Tracker (hypothetical).
- `ComparisonResult` — per-supply `SupplyCost` pairs, combined totals, delta,
  recommendation.

## 6. Data flow

1. **Config** — load `OCTOPUS_API_KEY` / `OCTOPUS_ACCOUNT` from `.env`; parse
   `--months N` (default 3) or `--from`/`--to`, plus `--format text|json`,
   `--gas-calorific-value` (default 39.5), `--verbose`.
2. **Discover** (`account.py`) — `GET /v1/accounts/{account}/` → electricity meter
   point (MPAN + serial), gas meter point (MPRN + serial), and **agreements**
   (tariff code + validity windows → identifies the real Flexible tariff and the
   true Tracker→Flexible switch date). Region letter (GSP group) from the
   electricity meter point detail.
3. **Resolve Tracker** (`tracker.py`) — find the current live Tracker product via
   `GET /v1/products/`, derive its electricity + gas tariff codes for our region.
   This is the tariff we'd switch *to*.
4. **Fetch consumption** (`client.py`) — half-hourly kWh for both supplies over the
   period, following pagination. Aggregate to daily (see §7, billing is per-day).
   Convert gas m³ → kWh.
5. **Fetch rates** (`rates.py`) — Flexible unit rates + standing charge, and Tracker
   daily unit rates + standing charge, for the same period (using `value_inc_vat`).
6. **Cost** (`costing.py`) — run the engine twice per supply (Flexible vs Tracker).
7. **Report** (`report.py`) — per-supply breakdown, combined total, recommendation.

## 7. Cost engine (the core)

Octopus bills **per day, rounding each day to the penny, then summing**. The engine
matches this:

```
for each day in period:
    day_cost = round_pennies(day_kwh × unit_rate_for(day))
energy_cost = sum(day_cost)
standing_cost = standing_charge_for_period   # date-matched, see below
subtotal = energy_cost + standing_cost
total = subtotal                              # rates used are inc-VAT (see VAT note)
```

- **Rate matching:** for each day, pick the rate whose `[valid_from, valid_to)`
  window covers it. Tracker = a different rate every day; Flexible = one rate until
  the next price-cap change. The same matching applies to standing charges, which
  are **tariff- and date-specific** (e.g. Flexible elec SC was 43.60p/day in March,
  42.18p Apr–May; Tracker SCs differ again).
- **VAT:** domestic energy VAT is **5%**. Octopus rounds each line item in
  **exc-VAT** terms (per-day energy, standing charge), sums them, then applies 5%
  VAT to the subtotal — verified because bill 1's 23 tracker days sum exactly to
  £44.56 → £55.88. The engine therefore uses `value_exc_vat` for line items and
  applies VAT to the subtotal (using `value_inc_vat` throughout would not
  reproduce the bills due to where rounding happens; the recommendation delta is
  unaffected since VAT scales both tariffs equally).
- **Gas m³ → kWh:** `kWh = m³ × 1.02264 × calorific_value / 3.6`. Calorific value
  varies (39.2 / 39.5 / 39.6 across the three bills); default 39.5, configurable.
  Tracker and Flexible gas rates are both p/kWh, so the same converted kWh feeds
  both — meaning the **savings difference is insensitive to the calorific value**;
  only the absolute pounds shift slightly. Evals use each bill's stated CV.
- **Rounding rule:** the exact per-day rounding convention (half-up vs floor, and
  whether standing charge rounds per-day or per-period) will be reverse-engineered
  to match the bills during TDD. Bill 1's daily Tracker tables are the
  highest-fidelity check (see §9).

Because both tariffs are costed from the *same* consumption, the comparison is
clean: only price differs.

## 8. Output

Plain-text report (via `rich`), e.g.:

```
Octopus Tariff Comparison  ·  1 Mar – 31 May 2026 (92 days)

Electricity   1,043 kWh    flexible £312.40   tracker £268.10   −£44.30
Gas           4,210 kWh    flexible £241.05   tracker £205.60   −£35.45
─────────────────────────────────────────────────────────────────────
Total                      flexible £553.45   tracker £473.70   −£79.75

→ SWITCH BACK to Tracker — it would have cost 14% (£79.75) less over this
  period. Figures are API-derived estimates incl. VAT, not your exact bill;
  Tracker prices change daily, so past savings don't guarantee future ones.
```

`--format json` emits the same data as structured JSON for scripting.

**Recommendation thresholds** (on the combined total over the period):
- Tracker cheaper by > ~2% → **SWITCH BACK**.
- Within ~2% either way → **MARGINAL — your call** (show the small delta).
- Tracker dearer by > ~2% → **STAY on Flexible**.

The report always states it's an estimate and that Tracker's daily pricing means
past savings don't guarantee future ones.

## 9. Evaluation / validation (using the provided bills)

The three PDF bills in `bills/` are ground truth. Evals live in `tests/`.

**Tier 1 — offline, penny-exact (primary).** Bill 1 (402259109) prints, for the
Tracker period 1–23 Mar 2026, 23 days of *daily kWh × daily rate = daily cost* for
both elec and gas. Transcribe into `tests/fixtures/bills.py` and assert the engine
reproduces:
- every daily cost,
- energy totals: electricity £44.56, gas £57.89,
- standing charges: elec 23 × 37.65p = £8.66, gas 23 × 28.52p = £6.56,
- VAT and bill totals: electricity £55.88, gas £67.67.

This pins down rate matching, gas m³→kWh (81.1 m³ × 1.02264 × 39.2 / 3.6 = 902.9
kWh), VAT, and the rounding rule, with no network or credentials.

**Tier 2 — offline, tolerance.** Flexible segments (bills 2 & 3, and bill 1's
24–31 Mar tail) print only monthly totals. Assert engine output matches within a
couple of pence. Reference figures:
- Bill 2 (Apr): elec 271.8 kWh @ 23.71p, SC 30 × 42.18p → £80.94 total;
  gas 75.7 m³ (→849.5 kWh @ 5.63p), SC 30 × 28.06p → £59.08 total.
- Bill 3 (May): elec 272.1 kWh @ 23.71p, SC 31 × 42.18p → £81.47 total;
  gas 47.5 m³ (→534.7 kWh @ 5.63p), SC 31 × 28.06p → £40.76 total.

**Tier 3 — online, optional (needs real API key).** Pull real daily consumption +
API rates for these exact periods, run the full pipeline, and assert it reproduces
the bill totals and that **API rates == bill-stated rates** (this also confirms the
region resolution and that the 2025-Budget discount is baked into API rates). Gated
behind an env flag; skipped by default in CI.

## 10. Error handling

- Missing/invalid credentials → clear message ("check `OCTOPUS_API_KEY` /
  `OCTOPUS_ACCOUNT` in `.env`").
- HTTP `401/403` → credentials problem; `429/5xx` → retry with backoff, then fail
  cleanly with the status.
- Smart-meter data lags ~1 day → if the requested period isn't fully covered, warn
  and report on the actual covered date range rather than silently under-counting.
- No meters / no agreement in period / no Tracker tariff for region → explain
  rather than crash.
- Gas consumption unit ambiguity (m³ vs kWh from the API) → resolved during
  implementation against Tier-3 eval; emit the assumed unit + CV in `--verbose`.

## 11. Known risks / things to verify in implementation

- **Exact rounding convention** — reverse-engineer against the bills (§7, §9).
- **Gas API units** — confirm whether the consumption endpoint returns m³ or kWh
  for this meter; convert accordingly.
- **Region/GSP letter** — auto-resolved from the API; the bill's "Postcode area
  alpha identifier: B" is *not* assumed to be the GSP group. Validated via Tier-3.
- **Current Tracker product code** — resolved at runtime from `/v1/products/`;
  Tracker products are versioned, so don't hard-code.
- **2025-Budget discount** — assumed baked into API unit rates (bills show no
  separate line); Tier-3 eval catches any mismatch.
- **API endpoint details** — confirm against current Octopus REST docs during
  planning (auth is HTTP Basic with the API key as username, blank password).

## 12. Success criteria

- Running `octopus-compare` with valid credentials prints, for the default last
  3 months, a per-supply and combined Flexible-vs-Tracker comparison and a clear
  switch recommendation.
- Tier-1 evals pass to the penny; Tier-2 within a couple of pence.
- The tool degrades gracefully (clear messages) on credential, coverage, and API
  errors.
