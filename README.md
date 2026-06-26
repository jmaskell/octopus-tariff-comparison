# octopus-compare

Compare what Octopus **Flexible**, **Tracker**, and a **12M Fixed** lock-in would
cost on your real usage, month by month, and get a recommendation. All three columns
are pure what-ifs (your consumption × each tariff's published rates) — none is your
actual bill. Tracker uses the version current each month; 12M Fixed uses today's
locked rate applied flat; the report marks the cheapest of the three each month.

## Setup

    python -m pip install -e ".[dev]"
    cp .env.example .env   # then paste your API key

Get your API key: https://octopus.energy/dashboard/new/accounts/personal-details/api-access

## Usage

    octopus-compare                       # last 3 months, Flexible vs latest Tracker vs 12M Fixed
    octopus-compare --from 2026-01-01 --to 2026-05-31   # backtest across your Tracker months
    octopus-compare --tracker-product SILVER-25-09-02   # pin a specific Tracker version
    octopus-compare --fixed-product OE-FIX-12M-26-06-24   # pin a specific 12M Fixed version
    octopus-compare --region C            # override the auto-derived region
    octopus-compare --format json

## Tests

    python -m pytest                      # offline unit + eval tests
    OCTOPUS_LIVE_EVAL=1 python -m pytest tests/test_live_eval.py   # live, needs API key

The offline suite validates the cost engine to the penny against three real
bills transcribed in `tests/fixtures/bills.py`.
