# Design: making `octopus-compare` honest

**Date:** 2026-06-26
**Status:** Approved (design), pending spec review
**Branch:** `fix/honest-comparison`

## Problem

An adversarial review (Codex gpt-5.5 + manual verification) found that the tool's
analysis and presentation can push the user toward the wrong tariff. Eight findings,
all confirmed against the code:

1. **Mixed time-basis (CRITICAL).** Flexible and Tracker are historical backtests
   (real past rates × past usage); the 12M Fixed column applies *today's* locked rate
   flat to those same past days (`tracker.py:202-213` `fixed_resolvers`). All three
   share one `✓` and one `SWITCH` verdict despite not being comparable.
2. **Tracker mislabelled (CRITICAL on long windows).** Header says
   "Tracker (switch-now) … current since {date}" (`report.py:133`) but the column is a
   multi-version *historical* backtest (`tracker.py:109-167`).
3. **Agile partial-data trap (CRITICAL).** Flexible costed on full daily data, Agile on
   half-hourly (`agile_pipeline.py:45-90`); only *total* absence of half-hourly errors.
   Partial gaps silently understate Agile and the block prints only Agile's kWh
   (`report.py:273`), hiding the mismatch.
4. **Gas unit auto-detect ~11× (CRITICAL).** `_resolve_gas_units` guesses m³ vs kWh from
   mean daily consumption (`consumption.py:73-88`); misclassification multiplies/divides
   the gas leg by ~11.22 and the resolved unit is surfaced nowhere (`cli.py:49-54` only
   echoes the *requested* mode under `--verbose`).
5. **Threshold ignores runner-up (HIGH).** `recommend()` (`report.py:81-87`) only guards
   cheapest-vs-Flexible, so it can confidently say SWITCH when the runner-up is pennies
   behind the winner.
6. **Agile decomposition can contradict the bill (HIGH).** "Why Agile is cheaper" is
   driven by energy-only `d.total_p` (`report.py:319-341`), excluding standing + VAT,
   so it can say "cheaper" next to a STAY verdict.
7. **No coverage disclosure (HIGH).** Missing supply/month costs become £0
   (`pipeline.py:85-112`); the user is never told a column was built from less data.
8. **Rounding `✓` on near-ties (MEDIUM).** Sub-£1 "wins" read as real decisions.

## Decisions (from brainstorming)

- **Time-basis:** keep Flexible vs Tracker as a like-for-like historical backtest (the
  only head-to-head with a `✓`/verdict). Present Fixed *separately* as a forward
  lock-in check measured against the Flexible backtest. Relabel Tracker.
- **Bad/ambiguous data:** still print the tables + a coverage summary, but **suppress
  the verdict** ("NO RECOMMENDATION") unless `--allow-partial-data` is set.
- **Near-tie band:** a challenger wins only if it beats the other by **>2% of the
  cheaper total AND >£5**; otherwise "too close to call".

## Design

### A. Report structure (the core reframe)

Replace the single mixed 3-column table with two bounded sections + footer:

```
Octopus Tariff Comparison · 2026-01-01 – 2026-03-31 · Region C

HISTORICAL BACKTEST — what you'd have paid (Flexible vs Tracker, same basis)
  Electricity:  Flexible | Tracker
  Gas:          Flexible | Tracker
  By month:     Flexible | Tracker     (✓ only when outside the tie band)
  Total:        £812      £820
  → STAY on Flexible — £8 (1.0%) cheaper than Tracker over this period.

FORWARD LOCK-IN CHECK — today's 12M Fixed rate on this usage (NOT a backtest)
  12M Fixed on this usage:  £798   (vs your £812 Flexible backtest: −£14, −1.7%)
  Note: today's locked rate applied flat — not what was offered during this period.
  → Locking Fixed now would have undercut Flexible here, but past ≠ future.

Coverage:  electricity 90/90 days · gas 90/90 days
Gas units: m³ (auto-detected, ×11.36 kWh/m³)
Figures incl. VAT, API-derived estimates — not your exact bill. [specific caveats]
```

- `ComparisonResult` keeps all three `SupplyCost`s; only presentation + recommendation
  separate them. The Flexible↔Tracker pair is the only like-for-like head-to-head.
- Fixed never shares a `✓` with the backtest columns. Its note compares Fixed-on-usage
  to the *Flexible backtest* as a reference point only.
- **Files:** `report.py` (rewrite `format_text`/`format_json` layout + `recommend`),
  `pipeline.py` (thread coverage + resolved gas unit through `ComparisonResult`).

### B. Recommendation engine (#5, #8, #2)

- Shared helper `verdict(status_quo_pounds, challenger_pounds, *, pct=Decimal("2"),
  abs_pounds=Decimal("5")) -> Verdict` returning `STAY` / `SWITCH` / `TOO_CLOSE`.
  Challenger wins (`SWITCH`) only if it beats the other by **>pct% of the cheaper AND
  >abs_pounds**; ties → `TOO_CLOSE`; status quo cheaper → `STAY`.
- Applied to **Flexible vs Tracker** (backtest verdict) and independently to **Fixed vs
  Flexible** (forward note). No cross-basis Tracker-vs-Fixed winner is ever produced.
- Monthly `✓` marks also respect the tie band (no `✓` when the month's two values are
  within band).
- Tracker label → "Tracker — historical versions used over this window: {codes}"; the
  header no longer advertises the latest version as if it priced the column.

### C. Coverage / data-integrity layer (#3, #7)

New module `coverage.py`.

- **3-way compare:** `expected` = days in `[period_from, period_to)`, **trimmed at the
  tail back to the latest day on which at least one supply has data** (so unsettled
  recent days — where every supply is empty — never trip it; leading absence is treated
  the same way). Per supply `missing = expected − priced_days`. Result carries
  per-supply `priced/expected` counts and the list of missing months.
- **Agile:** reference day-set = days with daily data; for each, check half-hourly
  presence. Flag days with **0 half-hourly slots** (missing) and an **aggregate
  divergence** check (Σ half-hourly kWh vs Σ daily kWh over the shared span > 2% →
  suspect). Show **Flexible's consumption** in the Agile block alongside Agile's.
- Data model: `Coverage` dataclass `{complete: bool, per_supply: {supply: (priced,
  expected, [missing_months])}, notes: [str]}`.
- When `complete` is False and `--allow-partial-data` is unset, the renderer prints
  tables + a `⚠ Coverage` summary and replaces the verdict with
  `→ NO RECOMMENDATION — <what's missing>; narrow the window with --from/--to or pass
  --allow-partial-data`.

### D. Gas units (#4)

- `_resolve_gas_units` returns `(unit: str, confident: bool)`.
- Under `auto`: mean daily in an **ambiguous band [4, 25)** (where high-m³ and low-kWh
  overlap) → `confident=False`. Treated as incomplete data per §C (suppress verdict,
  ask for explicit `--gas-units`). Outside the band, resolve as today (mean>15→kWh).
- Resolved unit + conversion factor is **always** rendered in the gas section (not just
  `--verbose`). Explicit `--gas-units m3|kwh` is always honoured silently and is always
  `confident=True`.
- Band edges (4, 25) are tunable constants in `consumption.py`.

### E. Agile decomposition honesty (#6)

- Headline verb ("Why Agile is **cheaper/more expensive**") driven by the **total bill
  delta** (`agile_total − flexible_total`, incl. standing + VAT), not energy-only.
- Energy split block retitled **"Energy-only price pattern (excl VAT & standing)"** with
  a **reconciliation line**: `energy Δ + standing Δ + VAT Δ = total Δ`.
- Rounding fix: derive one component (behavioural) as the residual so
  `structural_£ + behavioural_£` equals the energy Δ exactly; keep p/kWh figures.

## JSON output changes (`--format json`)

Breaking shape changes (acceptable — single-user tool):

- `recommendation` becomes per-comparison: `backtest.recommendation`
  (`STAY`/`SWITCH`/`TOO_CLOSE`) for Flexible-vs-Tracker.
- Fixed moves under `forward_lock_in: {fixed_total, delta_vs_flexible_pounds,
  delta_pct, verdict}`.
- New top-level `coverage` object and `gas_units: {resolved, confident, factor}`.
- Agile JSON gains `decomposition.reconciliation` and `total_delta_basis: "total"`.

## Testing (TDD)

Red→green per unit; existing tests asserting the old layout are updated to the new
behaviour as part of each red step. Run via `./.venv/bin/python -m pytest`.

- `coverage.py`: internal gap, trailing-lag tolerance, cross-supply month mismatch,
  partial-half-hourly day, daily-vs-hh divergence.
- `verdict()`: tie-band table (gap below/above £5 and 2%, both sides).
- `_resolve_gas_units`: confidence flag + ambiguous-band suppression; explicit override.
- `report` rendering: two-section layout, suppressed-verdict banner, resolved-unit line,
  monthly `✓` respects band.
- Agile decomposition: components reconcile to total Δ exactly; header follows total.
- Agile coverage: partial half-hourly suppresses verdict; Flexible consumption shown.

## Sequencing (dependency-ordered)

1. `coverage.py` (+ tests)
2. `verdict()` + recommendation rewrite (+ tests)
3. gas-unit confidence (+ tests)
4. 3-way report rewrite wiring coverage + gas unit (+ tests, update existing)
5. Agile decomposition reconciliation + Agile coverage (+ tests)
6. CLI `--allow-partial-data` wiring (+ test)

## Out of scope (YAGNI)

- An all-forward projection mode (rejected in favour of the same-basis backtest).
- Re-slicing Agile columns to a common day-set when partial (suppress verdict instead).
- Fetching true historical Fixed rates for a pure-backtest Fixed column.
