# octopus-compare

Compare what Octopus **Flexible** vs **Tracker** would cost on your real usage,
month by month, and get a switch recommendation. Both columns are pure what-ifs
(your consumption × each tariff's published rates) — neither is your actual bill.
The Tracker side uses the version current each month; the latest version
(today's switch-now rate) is named in the report header.

## Setup

    python -m pip install -e ".[dev]"
    cp .env.example .env   # then paste your API key

Get your API key: https://octopus.energy/dashboard/new/accounts/personal-details/api-access

## Usage

    octopus-compare                       # last 3 months, Flexible vs latest Tracker
    octopus-compare --from 2026-01-01 --to 2026-05-31   # backtest across your Tracker months
    octopus-compare --tracker-product SILVER-25-09-02   # pin a specific Tracker version
    octopus-compare --region C            # override the auto-derived region
    octopus-compare --format json

## Tests

    python -m pytest                      # offline unit + eval tests
    OCTOPUS_LIVE_EVAL=1 python -m pytest tests/test_live_eval.py   # live, needs API key

The offline suite validates the cost engine to the penny against three real
bills transcribed in `tests/fixtures/bills.py`.
