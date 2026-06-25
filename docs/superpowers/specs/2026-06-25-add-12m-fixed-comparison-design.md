# Add a Third Column: Octopus 12M Fixed — Design

**Date:** 2026-06-25
**Status:** Approved (design); pending implementation plan
**Builds on:** `2026-06-25-tariff-detail-and-latest-tracker-design.md` (the merged Flexible-vs-Tracker monthly backtest)

## 1. Purpose

`octopus-compare` currently shows two pure-what-if columns — **Flexible** and
**Tracker** — costed on real usage, month by month. This adds a **third column,
Octopus 12M Fixed**, so the report answers "of Flexible / Tracker / a 12-month
fixed lock-in, which is cheapest for my usage?"

## 2. Decisions (from brainstorming)

- **Product:** the standard **"Octopus 12M Fixed"** (`OE-FIX-12M-*`); today the
  current version is `OE-FIX-12M-26-06-24` ("Octopus 12M Fixed June 2026 v5",
  `available_to: null`). The meter-specific variants (Cosy/Go/Intelligent) are
  out of scope.
- **Fixed basis:** **today's locked rate, applied flat to every month.** A fixed
  deal is one rate locked at sign-up, so the Fixed column answers "if I lock in
  the rate available now, what would my usage have cost?" The rate is constant
  across the window; only usage varies month to month. (This differs from the
  Tracker column, which uses the version current each month.)
- **Layout:** **three absolute columns, cheapest marked.** Component blocks and
  the monthly table each gain a Fixed column; the monthly table marks the
  cheapest of the three per row (and on the total) with a `✓`.
- **Recommendation:** **3-way** — pick the cheapest of the three totals and frame
  it as a saving vs the user's current Flexible, with a one-line note of the
  runner-up; `MARGINAL` when the cheapest's saving vs Flexible is ≤ ~2%.
- **Always on:** the Fixed column is a standard part of the report (no opt-out
  flag), with a `--fixed-product CODE` override.

## 3. Grounding facts (verified against the live public API, 2026-06-25)

Fixed tariffs **are listed** (unlike Tracker): `GET /v1/products/?brand=OCTOPUS_ENERGY`
returns, among others:

| Code | Full name | available_from | available_to |
|---|---|---|---|
| `OE-FIX-12M-26-06-24` | Octopus 12M Fixed June 2026 v5 | 2026-06-24 | null (current) |

`is_variable: false`, `is_tracker: false`. The standard product's code prefix is
`OE-FIX-12M-`; the Cosy/Go/Intelligent fixed variants use different prefixes
(`COSY-FIX-12M-`, `GO-FIX-12M-`, `INTELLI-FIX-12M-`). Region is the trailing
letter of the tariff code, e.g. `E-1R-OE-FIX-12M-26-06-24-C`.

A fixed product publishes its locked unit rate + standing charge from its
`available_from` onward (the 12-month term); it does **not** publish rates for
dates before `available_from`. Hence the flat-rate handling in §5.

## 4. Output specification

```
Octopus Tariff Comparison · 1 Jan – 31 May 2026 (151 days) · Region C
Three tariffs costed on your actual usage — all pure what-ifs, none is your bill:
  Tracker (switch-now): SILVER-26-04-01 · current since 2026-04-01 (earlier months use the version current then)
  Fixed (12M lock-in):  OE-FIX-12M-26-06-24 · "Octopus 12M Fixed June 2026 v5" · today's locked rate, flat

Electricity              Flexible    Tracker      Fixed
  consumption           1,520 kWh   1,520 kWh   1,520 kWh
  energy (excl VAT)       £340.10     £305.40     £330.20
  standing charge          £63.20      £57.80      £61.00
  VAT (5%)                 £20.17      £18.16      £19.56
  ──────────────────────────────────────────────────────
  total                   £423.47     £381.36     £410.76

Gas                      Flexible    Tracker      Fixed
  ...                         ...         ...         ...

By month (elec + gas)    Flexible    Tracker      Fixed
  Jan 2026                £210.40    £194.00 ✓    £205.10
  Feb 2026                £198.20    £180.20 ✓    £193.40
  Mar 2026                £190.10    £175.10 ✓    £186.20
  Apr 2026                £158.40    £135.10 ✓    £152.30
  May 2026                £120.29     £99.43 ✓    £118.10
  ──────────────────────────────────────────────────────
  Total                   £877.39    £783.83 ✓    £855.10

→ Cheapest over this period: TRACKER — £783.83, 10.7% (£93.56) less than Flexible.
  (12M Fixed would save 2.5% / £22.29 vs Flexible.)
  Figures are API-derived estimates incl. VAT, not your exact bill; Tracker prices
  change daily and fixed/tracker rates change between sign-ups, so past savings
  don't guarantee future ones.
```

Rules:

- **Header** keeps the region and the Tracker switch-now line, and adds a **Fixed**
  line: code · display_name · "today's locked rate, flat".
- **Component blocks** (Electricity, Gas): a third **Fixed** column with the same
  rows (consumption / energy / standing / VAT / total).
- **Monthly table:** three absolute columns; the **cheapest of the three each row**
  is marked with a trailing `✓` (and the Total row likewise). No delta column —
  the recommendation carries the headline saving.
- **Recommendation:** `best = min(flexible_total, tracker_total, fixed_total)`.
  - If `best` is Flexible → `STAY on Flexible — cheapest over this period.`
  - Else → `Cheapest over this period: {NAME} — £{best}, {pct}% (£{saving}) less
    than Flexible`, where `saving = flexible_total − best`, `pct = saving /
    flexible_total`. If `pct ≤ 2%` → frame as `MARGINAL`.
  - A second line notes the runner-up's saving vs Flexible (the non-Flexible,
    non-best tariff).
- **`--format json`** gains `electricity.fixed` / `gas.fixed` component figures,
  a `fixed` meta object (product_code, display_name, available_from), a
  `fixed` value on each monthly row, `fixed_total`, and the cheapest label.

## 5. Fixed resolution + flat-rate mechanics

**Resolve the fixed product** (`resolve_fixed`):
- `GET /v1/products/?brand=OCTOPUS_ENERGY`; keep results whose `code` starts with
  `OE-FIX-12M-`; pick the current one (`available_to is None`, else the latest by
  `available_from`). Returns a `FixedProduct(product_code, display_name,
  available_from)`.
- `--fixed-product CODE` short-circuits to that code (fetch its detail for meta).
- Raises a clear error if none is found.

**Flat resolvers** (`fixed_resolvers`): because the current fixed product only
publishes rates from its `available_from` (typically after the backtest window),
do **not** date-match its rates against window days. Instead:
- Build the region tariff code `build_tariff_code(supply, product, region)`.
- Fetch the locked unit rate + standing charge querying at the product's own
  `available_from` (within its validity), and read the single value.
- Build an **all-covering** `RateLookup` (one window `date.min..date.max`) for each,
  so `rate_for(day)` returns the locked value for every day in the window.
- Return `(rate_for, sc_for)`.

The per-month Fixed `SupplyCost` is then computed by the existing penny-exact
`supply_cost()` over each month slice — identical machinery to Flexible/Tracker;
only the resolver differs (flat vs date-windowed).

## 6. Data model changes

- `FixedProduct` (new): `product_code: str`, `display_name: str`,
  `available_from: date`.
- `MonthlyRow` gains `fixed_pounds: Decimal`. A `.cheapest` helper (or report-side
  logic) identifies the min of flexible/tracker/fixed for the `✓` marker.
- `ComparisonResult` gains `elec_fixed: SupplyCost`, `gas_fixed: SupplyCost`,
  `fixed: FixedProduct`, and a `fixed_total` property. `recommend` is generalised
  to 3-way (returns the cheapest tariff name + the saving-vs-Flexible framing).

## 7. Module-level changes

- **`tracker.py`** — add `FixedProduct`, `resolve_fixed(client, override)`,
  `fixed_resolvers(client, supply, product, region)`. (Kept here as the sibling of
  the existing product-resolution helpers; no new module needed.)
- **`rates.py`** — small `flat_lookup(value) -> RateLookup` helper (one
  all-covering window), reused by the fixed resolver.
- **`config.py` / `cli.py`** — add `--fixed-product CODE` (default None).
- **`pipeline.py`** — in `_supply_breakdown`, also build the fixed flat resolvers
  and compute per-month Fixed `SupplyCost`s; aggregate `elec_fixed`/`gas_fixed`;
  resolve + carry the `FixedProduct` meta; add fixed totals to combined monthly
  rows. Same KeyError→`PricingError` guard already wraps the per-month
  `supply_cost` calls.
- **`report.py`** — Fixed column in component blocks and the monthly table with
  the `✓` cheapest-marker; 3-way `recommend`; `format_text`/`format_json` updated.

## 8. Testing & evaluation

- **resolve_fixed** — from a listing fixture with several `*-FIX-12M-*` products,
  picks the `OE-FIX-12M-*` with `available_to is None`; `--fixed-product`
  short-circuits; clear error when none found.
- **fixed_resolvers** — returns the locked value for any day, including days
  before the product's `available_from` (proves flat / no date-gating); region
  tariff code is built correctly per supply.
- **recommend (3-way)** — Flexible cheapest → STAY; Tracker cheapest → names
  Tracker + saving vs Flexible; Fixed cheapest → names Fixed; `MARGINAL` when the
  best saving ≤ 2%.
- **report** — text contains the Fixed column, the `✓` on the cheapest cell per
  row, the Fixed header line; JSON carries `fixed` component figures, meta,
  monthly `fixed` values, and `fixed_total`.
- **pipeline** — a three-tariff run produces `elec_fixed`/`gas_fixed`, fixed
  monthly totals summing to `fixed_total`, and a correct cheapest selection.
- **Existing tests** — updated for the new `ComparisonResult`/`MonthlyRow` shape;
  the penny-exact bill evals (`test_costing.py`) remain untouched and green.

## 9. Edge cases & error handling

- **No fixed product resolvable** → clear error (or omit the column) rather than a
  crash; the `--fixed-product` override path validates the code (404 → clear
  error naming it).
- **Fixed rate fetch returns nothing at `available_from`** → surfaced as the same
  friendly `PricingError` ("couldn't price … rates unavailable").
- **Ties in the monthly cheapest** (two tariffs equal) → mark the first in a fixed
  order (Flexible, Tracker, Fixed); document the tie-break.
- **Region per supply** — unchanged; the fixed tariff code reuses the derived
  region letter, overridable via `--region`.

## 10. Out of scope (YAGNI)

- The Cosy/Go/Intelligent fixed variants and non-12-month fixed terms.
- "Fixed version current each month" backtest (rejected in favour of today's flat
  rate).
- An opt-out flag for the Fixed column (it is always shown).
- A per-row delta column for three tariffs (the `✓` marker + recommendation cover
  the comparison).

## 11. Success criteria

- Running `octopus-compare` prints Flexible / Tracker / **Fixed** component blocks
  and a monthly table with the cheapest-of-three marked, plus a 3-way
  recommendation framed against Flexible.
- The header names the resolved Fixed product (today `OE-FIX-12M-26-06-24`);
  `--fixed-product` overrides it.
- The Fixed column uses today's locked rate applied flat across all months.
- Existing penny-exact evals still pass; the engine is untouched; failures degrade
  gracefully.
