# octopus-compare

Compare your actual Flexible Octopus spend against what Octopus Tracker would
have cost (electricity + gas), and get a switch recommendation.

## Setup

    python -m pip install -e ".[dev]"
    cp .env.example .env   # then paste your API key

Get your API key: https://octopus.energy/dashboard/new/accounts/personal-details/api-access

## Usage

    octopus-compare                       # last 3 months
    octopus-compare --months 1
    octopus-compare --from 2026-04-01 --to 2026-04-30
    octopus-compare --format json

## Tests

    python -m pytest                      # offline unit + eval tests
    OCTOPUS_LIVE_EVAL=1 python -m pytest tests/test_live_eval.py   # live, needs API key

The offline suite validates the cost engine to the penny against three real
bills transcribed in `tests/fixtures/bills.py`.
