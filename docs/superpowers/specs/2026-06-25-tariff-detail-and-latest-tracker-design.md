# Fine-Grained Tariff Comparison + Latest Tracker — Design

**Date:** 2026-06-25
**Status:** Approved (design); pending implementation plan
**Builds on:** `2026-06-25-octopus-tariff-comparison-design.md` (the existing tool)

## 1. Purpose

The existing `octopus-compare` tool prints a single per-supply **total** for the
household's actual tariff vs Octopus Tracker, plus a switch recommendation. Two
gaps make it hard to actually *decide* whether to switch:

1. **Not enough detail.** It only shows the per-supply total, even though the
   cost engine already computes consumption, energy, standing charge, and VAT
   for each tariff. You can't see *where* the difference comes from or *whether*
   the saving is consistent over time.
2. **Wrong Tracker version.** It compares against the newest Tracker the account
   was historically *on*, not the latest **published** version. Tracker is
   versioned and new sign-ups get the current version, so the historical one is
   not necessarily the rate you'd actually pay if you switched today.

This enhancement adds a fine-grained, per-tariff cost breakdown and makes the
comparison target the **latest published Tracker version**, so the report answers
"what would I pay, broken down, if I switched now?"

## 2. Decisions (from brainstorming)

- **Detail level:** component breakdown **plus** monthly breakdown.
  - Per supply: consumption / energy (excl VAT) / standing charge / VAT / total,
    for **Actual** and **Tracker** side by side, with the total delta.
  - A combined (electricity + gas) **monthly** table: per calendar month, the
    total on each tariff and the delta, then a grand total.
- **Tracker target:** **actively find the latest** published version (today that
  is `SILVER-26-04-01`, "Octopus Tracker April 2026 v1"), not the one from the
  account's history. Overridable with `--tracker-product CODE`. The resolved
  code, display name, and valid-from date are printed in the report.
- **Engine approach:** **slice & reuse** — call the existing penny-exact
  `supply_cost()` once per calendar month; the engine math is untouched. VAT is
  therefore rounded per month, which matches how Octopus actually bills. The
  headline total is the sum of the monthly totals.
- **Region:** auto-derived from the account's own tariff codes (no postcode
  needed); reused when building Tracker tariff codes so regional standing charges
  and unit rates are correct. Printed for transparency; optional `--region`
  override as a safety valve.

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

The version with `available_to: null` is the one currently open to new sign-ups —
i.e. the rate you'd actually pay if you switched today. This is the target.

Tariff codes embed the region as the trailing letter, e.g.
`E-1R-SILVER-26-04-01-B` (electricity, region B). A Tracker tariff keeps
publishing daily unit rates beyond its sign-up window, so rates for any of these
codes can be fetched for a recent comparison period.

## 4. Output specification

Plain-text report (illustrative numbers):

```
Octopus Tariff Comparison · 1 Apr – 25 Jun 2026 (86 days)
Comparing your actual tariff against the latest Octopus Tracker:
  SILVER-26-04-01 · "Octopus Tracker April 2026 v1" · current since 2026-04-01
  Region B

Electricity                    Actual      Tracker
  consumption                  742 kWh     742 kWh
  energy (excl VAT)            £166.30     £138.90
  standing charge               £36.27      £31.40
  VAT (5%)                      £10.13       £8.52
  ────────────────────────────────────────────────
  total                        £212.70     £178.82     −£33.88

Gas                            Actual      Tracker
  consumption                3,180 kWh   3,180 kWh
  energy (excl VAT)            £179.04     £151.20
  standing charge               £24.14      £22.80
  VAT (5%)                      £10.16       £8.70
  ────────────────────────────────────────────────
  total                        £213.34     £182.70     −£30.64

By month (elec + gas)          Actual      Tracker      Delta
  Apr 2026                     £158.40     £135.10     −£23.30
  May 2026                     £150.10     £128.40     −£21.70
  Jun 2026 (25 days)           £117.54      £98.02     −£19.52
  ──────────────────────────────────────────────────────────
  Total                        £426.04     £361.52     −£64.52

→ SWITCH BACK to Tracker — it would have cost 15.1% (£64.52) less over this
  period. Figures are API-derived estimates incl. VAT, not your exact bill;
  Tracker prices change daily, so past savings don't guarantee future ones.
```

Rules:

- **Columns are "Actual" vs "Tracker"** (not "Flexible"). The Actual side is
  computed per-day against the account's real agreements, so a window spanning
  the Tracker→Flexible switch is priced correctly day by day.
- **Header** prints the resolved Tracker `code · display_name · current since
  <available_from>` and the region letter, so the comparison target and regional
  pricing are always visible.
- **Component blocks** (Electricity, then Gas): rows for consumption, energy
  (excl VAT), standing charge, VAT (5%), and total, for both tariffs, with the
  delta on the total row.
- **Monthly table** combines electricity + gas per calendar month (the per-supply
  split is already covered by the component blocks). Partial months at the window
  edges show a day count, e.g. `Jun 2026 (25 days)`.
- **Recommendation** logic is unchanged (threshold on the combined grand-total
  delta: SWITCH BACK / MARGINAL / STAY), followed by the existing caveat line.
- **`--format json`** carries the same structure: per-supply component figures,
  the monthly rows, the tracker meta (code, display name, available_from), and
  the region.

## 5. Tracker discovery + region handling

**Region (per supply).** Extract the trailing region letter from the account's
own agreement tariff codes — electricity and gas independently. A postcode→GSP
lookup is *not* used: it is only needed when there is no account, and is ambiguous
at region boundaries. The account's tariff codes carry the exact region Octopus
bills, which is authoritative. `--region X` overrides if ever needed.

**Build a Tracker tariff code** from supply + product + region:
`E-1R-{product}-{region}` for electricity, `G-1R-{product}-{region}` for gas.

**Discover the latest version (chain-walk):**

1. **Seed** — find the newest Tracker product in the meter's agreement history
   (the existing history walk), giving a starting `SILVER-YY-MM-DD` code and the
   codename prefix. If `--tracker-product` is set, use that as the target
   directly and skip the walk.
2. **Walk** — `GET /products/{code}/`; read `available_to`.
   - `null` → this is the latest; stop.
   - otherwise → next code = `{codename}-{YY-MM-DD of available_to}`; repeat.
3. **Result** — `TrackerTariff(product_code, tariff_code, display_name,
   available_from)`, with the region-correct tariff code built per supply.
4. **Fallback** — if a constructed next code 404s, stop and return the last good
   version (best-effort), noting it in `--verbose`.

Discovery is seeded once (per account) and reused for both supplies; only the
final product's detail is needed for the printed meta.

## 6. Cost engine: slice & reuse

The penny-exact engine (`supply_cost`, `daily_energy_pence`, `standing_pence`,
VAT) is **not modified**. Instead:

- `pipeline.py` slices the daily-kWh series into calendar-month buckets and calls
  the existing `supply_cost()` once per (month, supply, tariff), using the same
  per-day actual resolvers and the Tracker resolvers.
- A new pure helper `sum_supply_costs(list[SupplyCost]) -> SupplyCost` aggregates
  monthly results component-wise (consumption, energy, standing, subtotal, VAT,
  total) to give the per-supply period figures and the combined grand total.
- VAT is therefore applied per month and summed — consistent across the headline,
  the component blocks, and the monthly table, and faithful to Octopus's monthly
  billing. The combined multi-month headline may differ from the old
  whole-period-VAT figure by a penny or two; this is acceptable and more correct.

**Eval safety:** the Tier-1 and Tier-2 bill evals all cover single-month windows,
which produce exactly one month bucket — identical to the whole-period
computation — so they continue to pass unchanged. No eval pins a multi-month
combined headline to the penny.

## 7. Data model changes

- `TrackerTariff` (in `tracker.py`) gains `display_name: str` and
  `available_from: date` alongside `product_code` / `tariff_code`.
- A `MonthlyRow` (or tuple) per calendar month: `month: date` (first of month),
  `days: int`, `actual: SupplyCost`, `tracker: SupplyCost` — held per supply, and
  combined (elec+gas) for the monthly table.
- `ComparisonResult` (in `report.py`) is extended to carry, per supply: the
  period `SupplyCost` for Actual and Tracker (from `sum_supply_costs`) and the
  list of monthly rows; plus the resolved tracker meta and the region letter.
  Existing `actual_total` / `tracker_total` / `delta` / `pct` / `recommend`
  semantics are preserved (now derived from the aggregated totals).

## 8. Module-level changes (summary)

- **`account.py`** — `region_letter(tariff_code)`; `tracker_tariff_code(supply,
  product, region)` helper.
- **`tracker.py`** — refactor to seed-from-history → `latest_tracker()`
  chain-walk → enriched `TrackerTariff`; honor `--tracker-product`; build
  region-correct codes; 404 fallback.
- **`config.py` / `cli.py`** — add `--tracker-product CODE` and optional
  `--region X`; thread into `Config`.
- **`costing.py`** — add `sum_supply_costs()` (pure aggregation); engine math
  untouched.
- **`pipeline.py`** — month-slice the daily kWh; per-month `supply_cost()` per
  supply per tariff; aggregate; assemble the enriched `ComparisonResult`.
- **`report.py`** — new component blocks + monthly table + header (tracker meta,
  region) in text; mirror the structure in JSON.

## 9. Testing & evaluation

- **Discovery** — mocked client returning a product chain; assert the walk
  returns the `available_to: null` version; assert next-code construction from an
  `available_to` date; assert 404 mid-walk falls back to the last good version;
  assert `--tracker-product` short-circuits the walk.
- **Region** — `region_letter` extraction; `tracker_tariff_code` building for
  electricity and gas.
- **Aggregation** — `sum_supply_costs` is component-wise correct; a single-month
  window yields a result identical to the whole-period computation (locks in
  Tier-1/Tier-2 eval compatibility); a multi-month window's grand total equals
  the sum of its monthly totals.
- **Report** — text output contains the component rows, the monthly rows with
  deltas, and the tracker code + region; JSON carries the same structure.
- **Existing bill evals** — unchanged; must still pass to the penny.
- **Tier-3 live (optional, env-gated)** — assert the resolved latest Tracker is
  the current `available_to: null` version and that the region matches the
  account's own tariff codes.

## 10. Edge cases & error handling

- **Partial months** at the window edges → bucketed normally; day count shown.
- **Smart-meter lag** → report the actual covered date range (existing behaviour).
- **Window spans the account's own tariff switch** → per-day actual resolvers
  already price each day against the agreement active that day.
- **No Tracker in history and no `--tracker-product`** → clear error: cannot
  determine a Tracker version; pass `--tracker-product`.
- **`--tracker-product` code 404s** → clear error naming the bad code.
- **Region mismatch / missing** → derive from any of the account's tariff codes;
  `--region` override available.

## 11. Out of scope (YAGNI)

- Comparing more than one Tracker version at once (override lets you inspect any
  single version; the default is the latest).
- Daily line-item table (monthly is the chosen granularity).
- Postcode→GSP lookup (the account already pins the region).
- Forward price projection; web UI; tariffs beyond Actual vs latest Tracker.

## 12. Success criteria

- Running `octopus-compare` prints, per supply, an Actual-vs-Tracker component
  breakdown and a combined monthly table with deltas and a grand total, plus the
  recommendation.
- The header shows the resolved **latest** Tracker code/name/date (today
  `SILVER-26-04-01`) and the region letter; `--tracker-product` and `--region`
  override correctly.
- A single-month window reproduces the existing penny-exact bill evals; the
  monthly rows sum to the grand total.
- The tool degrades gracefully (clear messages) on discovery 404s, missing
  Tracker history, and bad override codes.
