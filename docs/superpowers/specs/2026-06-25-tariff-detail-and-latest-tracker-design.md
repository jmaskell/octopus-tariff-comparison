# Fine-Grained Tariff Comparison + Backtest + Latest Tracker — Design

**Date:** 2026-06-25
**Status:** Approved (design); pending implementation plan
**Builds on:** `2026-06-25-octopus-tariff-comparison-design.md` (the existing tool)

## 1. Purpose

The existing `octopus-compare` tool prints a single per-supply **total** for the
household's actual tariff vs Octopus Tracker, plus a switch recommendation. Three
gaps make it hard to actually *decide* whether to switch:

1. **Not enough detail.** It only shows the per-supply total, even though the
   cost engine already computes consumption, energy, standing charge, and VAT for
   each tariff. You can't see *where* the difference comes from.
2. **No month-by-month backtest.** It shows one period total, not how the two
   tariffs compared *each month* — including the months you were actually on
   Tracker, where you'd want to see what Flexible would have cost instead.
3. **Wrong Tracker version for "switch now".** It compares against the newest
   Tracker the account was historically *on*, not the latest **published**
   version that a new sign-up would actually get.

This enhancement turns the report into a **month-by-month Flexible-vs-Tracker
backtest** with a per-supply component breakdown, costed on your real usage, and
makes the "switch now" reference the **latest published Tracker version**.

## 2. Decisions (from brainstorming)

- **Two consistent columns: Flexible vs Tracker**, each costed on your actual
  consumption. (Not "what you actually paid" — you explicitly want a clean
  tariff-vs-tariff comparison to weigh which is cheaper.)
  - **Flexible** = your Flexible Octopus rates by date, reconstructed for every
    month in the window (Flexible is a listed product, so historical rates are
    available even for months you weren't on it).
  - **Tracker** = the Tracker version that was the **current sign-up product**
    each day (chain-partitioned over time). Recent months therefore use the
    latest version (`SILVER-26-04-01`); historical months use the version current
    then. This is independent of which version you were personally on.
- **Neither column is your actual bill.** Both are computed from your real usage ×
  that tariff's published rates; what you actually paid never enters in. There is
  no reference to which tariff you were on — it is a pure tariff-vs-tariff what-if.
- **Detail level:** component breakdown **plus** monthly breakdown.
  - Per supply: consumption / energy (excl VAT) / standing charge / VAT / total,
    for Flexible and Tracker, with the total delta.
  - A combined (electricity + gas) **monthly** table: per calendar month, the
    total on each tariff and the delta; then a grand total.
- **Latest Tracker for "switch now":** the version with `available_to: null`
  (today `SILVER-26-04-01`) is identified and named in the header. Overridable
  with `--tracker-product CODE`.
- **Engine approach:** **slice & reuse** — call the existing penny-exact
  `supply_cost()` once per calendar month, per supply, per tariff. Engine math
  untouched; VAT rounds per month (matches Octopus's monthly billing); the
  headline total is the sum of monthly totals.
- **Region:** auto-derived from the account's own tariff codes (no postcode
  needed) and reused when building both Flexible and Tracker tariff codes, so
  regional standing charges and unit rates are correct. Printed for transparency;
  optional `--region` override as a safety valve.

## 3. Grounding facts (verified against the live public API, 2026-06-25)

Octopus Tracker (codename `SILVER`) is **not** discoverable by listing:
`GET /v1/products/?is_tracker=true` returns `count: 0`. But each version is
fetchable directly by code, and the versions form a self-describing chain — each
version's `available_to` equals the next version's `available_from`, and the code
is `SILVER-YY-MM-DD` of its start date:

| Version | Code | available_from | available_to |
|---|---|---|---|
| April 2025 v2 | `SILVER-25-04-15` | 2025-04-15 | 2025-09-02 |
| September 2025 v1 | `SILVER-25-09-02` | 2025-09-02 | 2026-04-01 |
| **April 2026 v1 (current)** | `SILVER-26-04-01` | 2026-04-01 | **null** |

The version with `available_to: null` is open to new sign-ups — the "switch now"
reference. The chain also **partitions time**: every day maps to exactly one
"current" Tracker version, which is what the Tracker column uses per day.

A Tracker version publishes daily unit rates for (at least) its active window, so
the Tracker column can be costed from these per-version rate series. **Flexible
Octopus is a listed product** whose unit rates / standing charges are published
historically per region, so the Flexible column can be reconstructed for any
past month. Tariff codes embed region as the trailing letter, e.g.
`E-1R-SILVER-26-04-01-B` (electricity, region B).

## 4. Output specification

Plain-text report over a window that spans both eras (illustrative numbers):

```
Octopus Tariff Comparison · 1 Jan – 31 May 2026 (151 days)
Flexible vs Octopus Tracker, costed on your actual usage · Region B
  Switch-now Tracker: SILVER-26-04-01 · "Octopus Tracker April 2026 v1" · current since 2026-04-01
  Earlier months use the Tracker version current that month.

Electricity                    Flexible    Tracker
  consumption                1,520 kWh   1,520 kWh
  energy (excl VAT)            £340.10     £305.40
  standing charge               £63.20      £57.80
  VAT (5%)                      £20.17      £18.16
  ────────────────────────────────────────────────
  total                        £423.47     £381.36     −£42.11

Gas                            Flexible    Tracker
  consumption                6,900 kWh   6,900 kWh
  energy (excl VAT)            £388.70     £342.10
  standing charge               £43.60      £41.20
  VAT (5%)                      £21.62      £19.17
  ────────────────────────────────────────────────
  total                        £453.92     £402.47     −£51.45

By month (elec + gas)      Flexible    Tracker      Delta
  Jan 2026                  £210.40     £194.00     −£16.40
  Feb 2026                  £198.20     £180.20     −£18.00
  Mar 2026                  £190.10     £175.10     −£15.00
  Apr 2026                  £158.40     £135.10     −£23.30
  May 2026                  £120.29     £ 99.43     −£20.86
  ──────────────────────────────────────────────────────────
  Total                     £877.39     £783.83     −£93.56

→ SWITCH BACK to Tracker — over this period it would have cost 10.7% (£93.56)
  less than Flexible. Figures are API-derived estimates incl. VAT, not your exact
  bill; Tracker prices change daily, so past savings don't guarantee future ones.
```

Rules:

- **Columns are "Flexible" vs "Tracker"** — two consistent counterfactual tariffs
  on the same consumption. Neither is your actual bill; both are your real usage ×
  that tariff's published rates, so every month has a Flexible and a Tracker figure
  regardless of which tariff you were on. A positive delta = Flexible cheaper that
  month, a negative delta = Tracker cheaper.
- **Header** prints the region, the switch-now Tracker
  `code · display_name · current since <available_from>`, and a note that earlier
  months use the then-current version.
- **Component blocks** (Electricity, then Gas): consumption / energy (excl VAT) /
  standing charge / VAT / total, for both tariffs, with the delta on the total.
  Over a multi-version window the Tracker side is the sum across versions.
- **Monthly table** combines electricity + gas per calendar month, with the delta.
  Partial months at the window edges show a day count, e.g. `May 2026 (24 days)`.
- **Delta sign:** Tracker − Flexible (negative = Tracker cheaper), consistent with
  the headline.
- **Recommendation** is computed on the combined grand-total delta over the window
  (SWITCH BACK / MARGINAL / STAY) followed by the existing caveat. For a pure
  "switch now" read, the recent rows (latest Tracker) are the relevant ones; the
  header names that version.
- **`--format json`** carries the same structure: per-supply component figures,
  the monthly rows (each with Flexible total, Tracker total, delta, and days), the
  switch-now tracker meta, and the region.

## 5. Rate resolution

All four resolvers are **per-day** and **region-correct** (each tariff code built
as `{E|G}-1R-{product}-{region}` using the account's own region letter, per
supply).

**Flexible (by date).** Resolve the household's Flexible product/tariff code from
its Flexible agreement(s). Fetch unit rates + standing charges across the window;
for months outside any Flexible agreement, use the Flexible product current that
day (Flexible is listed, so this is resolvable). Build a per-day Flexible rate +
standing-charge lookup. Price-cap changes are time-windowed within the rate
series and matched per day.

**Tracker (current version, by date).** Gather the set of Tracker versions whose
`[available_from, available_to)` intersects the window:
- older anchors from the account's Tracker agreement history (the codes the
  account was on),
- the forward **chain-walk** to the latest (`available_to: null`): from a seed
  code, `GET /products/{code}/`; if `available_to` is null it's the latest, else
  next code = `{codename}-{YY-MM-DD of available_to}`, repeat.

Fetch each gathered version's unit rates + standing charges over (its slice of)
the window, then build a per-day lookup that picks, for each day, the version
whose `[available_from, available_to)` covers it. The latest version (for the
header) is the one with `available_to: null`. `--tracker-product CODE`
short-circuits version selection to a single fixed code. A 404 on a constructed
code stops the walk (best-effort), noted in `--verbose`; a window day with no
resolvable Tracker version is reported as a gap rather than mis-priced.

## 6. Cost engine: slice & reuse

The penny-exact engine (`supply_cost`, `daily_energy_pence`, `standing_pence`,
VAT) is **not modified**. `pipeline.py`:

- slices the daily-kWh series into calendar-month buckets, and
- calls `supply_cost()` once per (month, supply, tariff), passing the Flexible or
  Tracker per-day resolvers from §5.

A new pure helper `sum_supply_costs(list[SupplyCost]) -> SupplyCost` aggregates
monthly results component-wise to give the per-supply period figures and the
combined grand total. VAT is applied per month and summed — consistent across
headline, component blocks, and the monthly table.

**Eval safety:** the existing Tier-1/Tier-2 bill evals cover single-month windows
on the household's *actual* tariff. They are re-expressed against the matching
column (Flexible or Tracker-current-version) for those single months, which —
being one month bucket — equals the whole-period computation, so they continue to
pin the engine to the penny.

## 7. Data model changes

- `TrackerVersion` (new, in `tracker.py`): `product_code`, `display_name`,
  `available_from: date`, `available_to: date | None`. The chain-walk returns the
  ordered list; the `available_to is None` one is the "switch-now" latest.
- `MonthlyRow`: `month: date` (first of month), `days: int`,
  `flexible: SupplyCost`, `tracker: SupplyCost` — held per supply, and combined
  (elec+gas) for the monthly table.
- `ComparisonResult` (in `report.py`): per supply, the period `SupplyCost` for
  Flexible and Tracker (from `sum_supply_costs`) and the list of monthly rows;
  plus the switch-now tracker meta and the region letter. `actual_total` /
  `tracker_total` are renamed to `flexible_total` / `tracker_total`;
  `delta` / `pct` / `recommend` semantics are preserved over those totals.

## 8. Module-level changes (summary)

- **`account.py`** — `region_letter(tariff_code)`; `tariff_code(supply, product,
  region)` builder; surface the Flexible product code and the Tracker history
  anchors from agreements.
- **`tracker.py`** — chain-walk returning the ordered `TrackerVersion` list +
  the latest; gather window-intersecting versions; build the per-day Tracker
  rate/standing-charge resolver; honour `--tracker-product`; 404 fallback.
- **`rates.py`** — build a per-day Flexible resolver and a per-day multi-version
  Tracker resolver (compose existing `RateLookup`s; pick by date).
- **`config.py` / `cli.py`** — add `--tracker-product CODE` and optional
  `--region X`; thread into `Config`.
- **`costing.py`** — add `sum_supply_costs()` (pure aggregation); engine math
  untouched.
- **`pipeline.py`** — month-slice; per-month `supply_cost()` per supply per
  tariff using the §5 resolvers; aggregate; assemble the enriched result.
- **`report.py`** — component blocks + monthly table (with delta) + header
  (region, switch-now tracker); mirror in JSON.

## 9. Testing & evaluation

- **Discovery** — mocked product chain → chain-walk returns the ordered versions
  and identifies the `available_to: null` latest; next-code construction from an
  `available_to` date; 404 mid-walk falls back; `--tracker-product`
  short-circuits.
- **Per-day resolvers** — Tracker resolver picks the correct version per day
  across a version boundary; Flexible resolver matches price-cap windows; region
  letter is applied to both, per supply.
- **Region** — `region_letter` extraction and tariff-code building (elec + gas).
- **Aggregation** — `sum_supply_costs` is component-wise correct; a single-month
  window equals the whole-period computation (locks Tier-1/Tier-2 compatibility);
  a multi-month grand total equals the sum of monthly totals.
- **Report** — text contains component rows, monthly rows with deltas, region,
  and the switch-now tracker code; JSON mirrors it.
- **Existing bill evals** — re-expressed against the matching column for those
  single-month windows; still pass to the penny.
- **Tier-3 live (optional, env-gated)** — the resolved latest is the current
  `available_to: null` version; region matches the account; the per-day Tracker
  resolver reproduces known daily rates across a version boundary.

## 10. Edge cases & error handling

- **Partial months** at window edges → bucketed normally; day count shown.
- **Month spanning a Tracker version boundary** → the per-day Tracker resolver
  prices each day on its current version.
- **Smart-meter lag** → report the actual covered date range (existing behaviour).
- **Window day with no resolvable Tracker version** (older than any gathered
  anchor) → reported as a gap, not mis-priced.
- **No Flexible agreement for early months** → use the Flexible product current
  that day (listed product).
- **`--tracker-product` code 404s** → clear error naming the bad code.
- **Region missing** → derive from any account tariff code; `--region` override.

## 11. Out of scope (YAGNI)

- A "what you actually paid" column or any reference to which tariff you were on
  (the report is a pure tariff-vs-tariff what-if).
- Per-account historical Tracker-version selection (the Tracker column uses the
  then-current product, by decision).
- Daily line-item table (monthly is the chosen granularity).
- Postcode→GSP lookup (the account already pins the region).
- Forward price projection; web UI; tariffs beyond Flexible vs Tracker.

## 12. Success criteria

- Running `octopus-compare` over a window that spans both eras prints, per supply,
  a Flexible-vs-Tracker component breakdown, and a combined **monthly** table with
  per-month deltas, plus a grand total and a recommendation.
- The header shows the region and the switch-now **latest** Tracker
  (today `SILVER-26-04-01`); earlier months are priced on the then-current
  version; `--tracker-product` and `--region` override correctly.
- A single-month window reproduces the existing penny-exact bill evals; the
  monthly rows sum to the grand total.
- The tool degrades gracefully (clear messages) on discovery 404s, version gaps,
  missing Flexible/Tracker data, and bad override codes.
