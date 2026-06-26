# Agile: Hour-of-Day Breakdown + Structural-vs-Behavioural Decomposition — Design

**Date:** 2026-06-26
**Status:** Approved (design); pending implementation plan
**Builds on:** `2026-06-26-agile-comparison-design.md` (the `octopus-compare agile` subcommand)

## 1. Purpose

The `agile` subcommand reports that Agile is cheaper (or dearer) but not **why**.
A saving can come from two very different sources, and they have opposite
implications:

- **Structural** — Agile's prices are simply lower (or higher) *on average* than
  the Flexible flat rate. You get this regardless of behaviour.
- **Behavioural** — your usage happens to fall at cheaper- (or dearer-) than-
  average times of day. This is the part you can change by shifting load.

This adds, to every `agile` run: (a) a **decomposition** splitting the
Flexible-vs-Agile difference into structural and behavioural components, and
(b) an **hour-of-day table** showing when usage peaks against what Agile charges
then. Both are direction-aware: they read correctly whether Agile is cheaper or
more expensive.

## 2. Decisions (from brainstorming)

- **Always shown.** Both pieces print on every `agile` run (no new flag).
- **Decomposition basis: energy only, excl. VAT & standing.** Timing only moves
  the energy component; the standing charge is a fixed per-day cost. Computing the
  decomposition on the energy unit price keeps the "when you use power" story
  clean. (It therefore won't equal the headline total saving, which includes
  standing + VAT — stated in the output.)
- **Time-average baseline over ALL period slots.** The "if you used power evenly"
  price is the mean Agile rate across every half-hour in the window, weighting each
  half-hour equally — not just the slots consumed in — so the household's own
  behaviour doesn't leak into the baseline it's measured against.
- **Full 24-row hour-of-day table** with a usage bar, cheap/DEAR markers, and a
  one-line cheapest-vs-dearest-hours summary.
- **Direction-aware wording.** Header and each component line flip their wording by
  sign (cheaper/dearer, saving/extra cost); JSON carries raw signed numbers.
- **Plumbing: `agile_resolvers` returns the rate map** as a third value
  (`rate_for, sc_for, rate_map`) — no extra API calls.

## 3. Data model & module changes

- **`agile.py`** — `agile_resolvers(...)` returns `(rate_for, sc_for, rate_map)`,
  where `rate_map: dict[datetime, Decimal]` is the merged instant→exc-VAT-pence map
  it already builds (`by_instant`). No other behaviour change.
- **`agile_breakdown.py`** (new) — keeps `agile_insight.py` focused on the existing
  summary. Holds:
  - `Decomposition(flex_p, time_avg_p, load_p, structural_p, behavioural_p,
    total_p, structural_pounds, behavioural_pounds, total_pounds, total_kwh)` —
    all `Decimal`; the `_p` fields are exc-VAT pence/kWh, `_pounds` are £ over the
    period (can be negative).
  - `HourBucket(hour: int, usage_pct: Decimal, avg_price_p: Decimal,
    marker: str | None)` — `marker ∈ {"cheap", "dear", None}`; `hour` is the
    London-local hour 0–23.
  - `AgileBreakdown(decomposition: Decomposition, by_hour: list[HourBucket],
    cheapest6_usage_pct: Decimal, dearest6_usage_pct: Decimal)`.
  - `compute_breakdown(halfhourly_kwh, rate_map, flex_effective_p,
    agile_effective_p, total_kwh, period_from, period_to) -> AgileBreakdown`.
- **`agile_pipeline.py`** — unpack the new `rate_map`; after `compute_insight`,
  call `compute_breakdown(...)` (passing `insight.flex_effective_p`,
  `insight.agile_effective_p`, and `elec_agile.consumption_kwh`); carry
  `breakdown` on `AgileResult`.
- **`report.py`** — `AgileResult` gains `breakdown: AgileBreakdown`; new
  `_agile_decomposition_lines` / `_agile_hour_lines` feed `format_agile_text`;
  `format_agile_json` gains the `breakdown` object.

## 4. Computation

**Period filter.** Restrict `rate_map` to instants in
`[period_from 00:00 UTC, period_to 00:00 UTC]` inclusive — the requested window —
dropping the `+1` boundary-day rates the upper-boundary fix fetches. Call the
filtered values `period_rates: dict[datetime, Decimal]`.

**Decomposition** (reusing the already-computed effective prices):
- `time_avg_p = mean(period_rates.values())` — each half-hour weighted equally.
- `structural_p  = flex_effective_p − time_avg_p`     (Agile cheaper on avg if > 0)
- `behavioural_p = time_avg_p − agile_effective_p`     (cheaper-time usage if > 0)
- `total_p       = flex_effective_p − agile_effective_p`
  (identically `structural_p + behavioural_p`)
- `structural_pounds = structural_p × total_kwh / 100` (likewise behavioural, total).
- `flex_p = flex_effective_p`, `load_p = agile_effective_p` (carried for display).

**Hour-of-day** (24 `HourBucket`s, London-local hour):
- `usage_pct[h] = (Σ kwh in hour h) / total_kwh × 100` — from `halfhourly_kwh`.
- `avg_price_p[h] = mean(rate of every period slot in hour h)` — from
  `period_rates` (all slots, not just consumed).
- `marker[h]` = `"cheap"` if `avg_price_p[h] < time_avg_p × 0.8`, `"dear"` if
  `> time_avg_p × 1.3`, else `None`.
- A bucket whose hour has no period slots (window shorter than a full day) gets
  `avg_price_p = 0` and `marker = None`; usage_pct still reflects any usage.

**Summary.** Rank hours by `avg_price_p`; `cheapest6_usage_pct` = Σ usage_pct of
the 6 lowest-priced hours, `dearest6_usage_pct` = Σ usage_pct of the 6 highest. A
flat user would have 25% in each.

**Guards.** The pipeline already raises before this runs when there's no
half-hourly data, so `total_kwh > 0` and `period_rates` is non-empty; still guard
division-by-zero on `total_kwh` and empty `period_rates` defensively (return zeros).

## 5. Output specification

Slots between the existing `Time-of-use insight` block and the recommendation.
**Example — Agile cheaper:**

```
Why Agile is cheaper (energy only, excl VAT & standing)
  Flexible flat rate                 23.96 p/kWh
  Agile if you used power evenly     16.91 p/kWh   (time-average)
  Agile on your actual usage         18.18 p/kWh   (your load)
  ──────────────────────────────────────────────
  Structural (Agile cheaper on avg)  +7.05 p/kWh    £43.85
  Behavioural (you use at dearer times)  −1.27 p/kWh   −£7.89
  Net saving                         +5.78 p/kWh    £35.95

Hour-of-day (London)       usage   avg Agile
  00:00                     1.7%   15.1p  ███
  ...
  14:00                     4.8%   10.2p  ██████████  cheap
  ...
  18:00                     9.4%   32.5p  ████████  DEAR
  19:00                    11.3%   21.5p  ███████████
  ...
  Usage in 6 cheapest hours: 29% · 6 dearest: 41%  (flat user: 25% / 25%)
```

**Direction-aware wording** (driven by each value's sign):

| Line | value > 0 | value < 0 | value == 0 |
|---|---|---|---|
| Header | `Why Agile is cheaper` | `Why Agile is more expensive` | `Flexible vs Agile — energy breakdown` |
| Structural | `Agile cheaper on average` | `Agile dearer on average` | `Agile same on average` |
| Behavioural | `you use at cheaper times` | `you use at dearer times` | `your timing is neutral` |
| Net | `Net saving` | `Net extra cost` | `Net: no difference` |

Rules:
- The three reference-price rows and the hour-of-day table are facts — identical
  regardless of direction.
- Each component shows a **signed** p/kWh (`+`/`−`) and a signed £ amount; negatives
  render as `−£7.89` (leading minus before the `£`, fixing the `£-` ordering for
  these lines).
- `cheap`/`DEAR` markers use the 0.8× / 1.3× thresholds vs `time_avg_p`.
- The usage bar is one `█` per 0.5% of usage (rounded).

**`--format json`** gains, on the existing agile object:

```json
"breakdown": {
  "decomposition": {
    "flex_p": "23.96", "time_avg_p": "16.91", "load_p": "18.18",
    "structural_p": "7.05", "behavioural_p": "-1.27", "total_p": "5.78",
    "structural_pounds": "43.85", "behavioural_pounds": "-7.89",
    "total_pounds": "35.95", "total_kwh": "622.0"
  },
  "by_hour": [
    {"hour": 0, "usage_pct": "1.7", "avg_price_p": "15.05", "marker": null},
    {"hour": 18, "usage_pct": "9.4", "avg_price_p": "32.45", "marker": "dear"}
  ],
  "cheapest6_usage_pct": "29.0", "dearest6_usage_pct": "41.0"
}
```

JSON carries raw signed numbers; consumers derive direction. `by_hour` has 24
entries ordered hour 0→23.

## 6. Testing & evaluation

- **`test_agile_breakdown.py`** (new):
  - Decomposition algebra: `structural_p + behavioural_p == total_p`; `_pounds ==
    _p × total_kwh / 100`; on a fixture where load skews to dear hours,
    `behavioural_p < 0`; on a fixture where the time-average exceeds the Flexible
    flat rate, `structural_p < 0` (the inverse / Agile-dearer case).
  - Hour buckets: `usage_pct` sums to ~100; per-hour `avg_price_p` correct; markers
    at the 0.8×/1.3× thresholds; an hour with no slots → `avg_price_p == 0`,
    `marker is None`.
  - Summary: correct 6-cheapest / 6-dearest hour selection and usage shares.
  - Period filter: a rate stamped on the `+1` boundary day is excluded from
    `time_avg_p`.
- **`test_agile.py`**: update the `agile_resolvers` test to unpack
  `(rate_for, sc_for, rate_map)` and assert `rate_map` carries the merged instants
  (including the multi-version merge).
- **`test_agile_pipeline.py`**: `result.breakdown` populated — decomposition totals
  reconcile (`structural + behavioural == total`), 24 hour buckets present.
- **`test_agile_report.py`**:
  - Cheaper case: text contains `Why Agile is cheaper`, the three price rows,
    `Structural`, `Behavioural`, `Net saving`, hour rows, and the summary line.
  - **Inverse case**: a result where Agile is dearer renders `Why Agile is more
    expensive`, `dearer on average` (when structural < 0), and `Net extra cost`.
  - JSON has `breakdown.decomposition`, `by_hour` (length 24), and the summary
    shares; signed values stringify with their sign.
- Existing suite stays green; the only ripple is the `agile_resolvers` three-value
  return (its callers in the pipeline and its unit test).

## 7. Edge cases

- **Window shorter than a day** → some hours have no period slots; those buckets
  show `avg_price_p = 0`, `marker = None`; usage_pct still reflects usage.
- **All usage in one hour** → that hour 100%, others 0%; summary still computes.
- **Agile dearer overall** (`total_p < 0`) → header/labels flip; £ figures negative.
- **DST days** → hour-of-day uses London-local hour; a 23-/25-hour DST day's extra
  or missing local hour is handled naturally by bucketing on local hour.
- **Empty input** → guarded upstream (pipeline raises); defensive zero-guards remain.

## 8. Out of scope (YAGNI)

- A load-shift "what-if" simulator (estimate savings from moving X% off peak).
- A `--by-hour` flag or any opt-in/opt-out (both pieces are always shown).
- Day-of-week or seasonal breakdowns.
- Changing the existing `Time-of-use insight` block, headline totals, or
  recommendation logic.

## 9. Success criteria

- Every `agile` run prints the decomposition (three reference prices + structural /
  behavioural / net, signed) and the 24-row hour-of-day table with the
  cheapest-vs-dearest summary.
- Wording is correct in both directions (Agile cheaper *and* Agile dearer).
- The decomposition is energy-only with the time-average taken over all period
  slots; `structural_p + behavioural_p == total_p` exactly.
- `--format json` exposes the full `breakdown` with raw signed figures.
- No extra API calls (the rate map is reused from `agile_resolvers`); existing
  tests and the daily report stay green.
