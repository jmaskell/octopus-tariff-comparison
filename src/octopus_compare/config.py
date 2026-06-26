import argparse
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
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
    tracker_product: str | None = None
    region: str | None = None
    fixed_product: str | None = None
    command: str = "compare"
    agile_product: str | None = None
    peak_window: tuple = (time(16, 0), time(19, 0))


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _parse_time(value: str) -> time:
    return datetime.strptime(value.strip(), "%H:%M").time()


def _parse_peak_window(value: str) -> tuple:
    start, end = value.split("-")
    return (_parse_time(start), _parse_time(end))


def load_config(argv: list[str], env: dict[str, str], today: date) -> Config:
    parser = argparse.ArgumentParser(prog="octopus-compare")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--months", type=int, default=3)
    common.add_argument("--from", dest="from_", type=_parse_date)
    common.add_argument("--to", dest="to", type=_parse_date)
    common.add_argument("--format", choices=["text", "json"], default="text")
    common.add_argument("--gas-calorific-value", type=Decimal, default=Decimal("39.5"))
    common.add_argument("--gas-units", choices=["auto", "m3", "kwh"], default="auto")
    common.add_argument("--verbose", action="store_true")
    common.add_argument("--tracker-product", dest="tracker_product", default=None)
    common.add_argument("--region", dest="region", default=None)
    common.add_argument("--fixed-product", dest="fixed_product", default=None)

    sub = parser.add_subparsers(dest="command")
    sub.add_parser("compare", parents=[common])
    agile_p = sub.add_parser("agile", parents=[common])
    agile_p.add_argument("--agile-product", dest="agile_product", default=None)
    agile_p.add_argument("--peak-window", dest="peak_window",
                         type=_parse_peak_window, default=(time(16, 0), time(19, 0)))

    # No subcommand → behave as 'compare' with the common flags.
    if argv and argv[0] in ("compare", "agile"):
        args = parser.parse_args(argv)
    else:
        args = parser.parse_args(["compare", *argv])

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
        tracker_product=args.tracker_product,
        region=args.region,
        fixed_product=args.fixed_product,
        command=args.command or "compare",
        agile_product=getattr(args, "agile_product", None),
        peak_window=getattr(args, "peak_window", (time(16, 0), time(19, 0))),
    )
