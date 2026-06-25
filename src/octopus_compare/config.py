import argparse
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal


class ConfigError(Exception):
    pass


@dataclass
class Config:
    api_key: str
    account: str
    period_from: date
    period_to: date
    output_format: str
    gas_calorific_value: Decimal
    gas_units: str
    verbose: bool


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def load_config(argv: list[str], env: dict[str, str], today: date) -> Config:
    parser = argparse.ArgumentParser(prog="octopus-compare")
    parser.add_argument("--months", type=int, default=3)
    parser.add_argument("--from", dest="from_", type=_parse_date)
    parser.add_argument("--to", dest="to", type=_parse_date)
    parser.add_argument("--format", choices=["text", "json"], default="text")
    parser.add_argument("--gas-calorific-value", type=Decimal, default=Decimal("39.5"))
    parser.add_argument("--gas-units", choices=["auto", "m3", "kwh"], default="auto")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    api_key = env.get("OCTOPUS_API_KEY", "").strip()
    account = env.get("OCTOPUS_ACCOUNT", "").strip()
    if not api_key or not account:
        raise ConfigError(
            "Missing credentials. Set OCTOPUS_API_KEY and OCTOPUS_ACCOUNT in .env"
        )

    period_to = args.to or today
    period_from = args.from_ or (today - timedelta(days=30 * args.months))

    return Config(
        api_key=api_key,
        account=account,
        period_from=period_from,
        period_to=period_to,
        output_format=args.format,
        gas_calorific_value=args.gas_calorific_value,
        gas_units=args.gas_units,
        verbose=args.verbose,
    )
