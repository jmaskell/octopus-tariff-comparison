# octopus-compare

Compare what Octopus **Flexible**, **Tracker**, and a **12M Fixed** lock-in would
cost on your real usage, month by month, and get a recommendation. All comparisons
are pure what-ifs (your consumption × each tariff's published rates) — none is your
actual bill.

## Setup

    python -m pip install -e ".[dev]"
    cp .env.example .env   # then paste your API key

Get your API key: https://octopus.energy/dashboard/new/accounts/personal-details/api-access

## Usage

    octopus-compare                       # last 3 months, Flexible vs Tracker vs 12M Fixed
    octopus-compare --from 2026-01-01 --to 2026-05-31   # backtest across your Tracker months
    octopus-compare --tracker-product SILVER-25-09-02   # pin a specific Tracker version
    octopus-compare --fixed-product OE-FIX-12M-26-06-24   # pin a specific 12M Fixed version
    octopus-compare --region C            # override the auto-derived region
    octopus-compare --allow-partial-data  # skip the NO RECOMMENDATION guard on incomplete data
    octopus-compare --format json

    octopus-compare agile                 # Flexible vs Agile (electricity only), half-hourly backtest
    octopus-compare agile --from 2026-01-01 --to 2026-05-31
    octopus-compare agile --agile-product AGILE-24-10-01   # pin a specific Agile version
    octopus-compare agile --peak-window 17:00-20:00        # redefine the peak band (default 16:00-19:00)
    octopus-compare agile --allow-partial-data             # skip the guard on partial half-hourly data

### 3-way report output

The default report has two sections:

**HISTORICAL BACKTEST (Flexible vs Tracker)** — costs your real usage at the Tracker
rate(s) in force each month and compares them to Flexible on the same time basis.
Tracker is labelled by the historical product version(s) used, not a hypothetical
"switch now" rate. The recommendation here is purely about the historical period you
selected.

**FORWARD LOCK-IN CHECK** — takes today's 12M Fixed rate and applies it flat to your
past usage. This is *not* a backtest of what Fixed would have cost in that period — it
shows whether the current lock-in price would undercut your Flexible spend over the
same kWh. It is clearly labelled as "today's rate on past usage."

A winner is only declared when the difference clears **both** a >2% and a >£5
threshold. Smaller differences are reported as "too close to call" — pick based on
price stability, not the number.

If coverage is incomplete (missing months) or the gas unit is ambiguous, the report
shows a **NO RECOMMENDATION** banner and suppresses all verdict ticks. Pass
`--allow-partial-data` to override this guard and see the numbers anyway. The
resolved gas unit and a coverage summary are always shown regardless.

The `agile` subcommand costs your real half-hourly electricity usage against Agile's published
half-hourly rates for the same dates (a pure what-if backtest), reports Flexible-vs-Agile totals
and a monthly table, and a time-of-use insight block (effective p/kWh, peak share, cheapest/priciest
half-hours, negative-price slots), plus a breakdown of *why* Agile is cheaper or dearer — splitting
the difference into a **structural** part (Agile's average price vs the Flexible flat rate) and a
**behavioural** part (whether your usage falls at cheaper- or dearer-than-average times) — and an
hour-of-day table of usage vs price. Gas is excluded — Agile is electricity-only. Incomplete
half-hourly coverage also triggers a NO RECOMMENDATION banner; pass `--allow-partial-data` to override.

## Tests

    python -m pytest                      # offline unit + eval tests
    OCTOPUS_LIVE_EVAL=1 python -m pytest tests/test_live_eval.py   # live, needs API key

The offline suite validates the cost engine to the penny against three real
bills transcribed in `tests/fixtures/bills.py`.
