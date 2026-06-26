import os
import sys
from datetime import date

from dotenv import dotenv_values

from octopus_compare.client import OctopusClient, ApiError
from octopus_compare.config import load_config, ConfigError
from octopus_compare.agile_pipeline import run_agile_comparison
from octopus_compare.pipeline import run_comparison, PricingError
from octopus_compare.report import format_text, format_json, format_agile_text, format_agile_json


def _load_env() -> dict:
    env = {**dotenv_values(".env"), **os.environ}
    return env


def _today() -> date:
    return date.today()


def _build_client(cfg) -> OctopusClient:
    return OctopusClient(cfg.api_key)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    env = _load_env()
    try:
        cfg = load_config(argv, env, _today())
    except ConfigError as e:
        print(str(e), file=sys.stderr)
        return 2

    try:
        client = _build_client(cfg)
        if cfg.command == "agile":
            result = run_agile_comparison(client, cfg)
        else:
            result = run_comparison(client, cfg)
    except ApiError as e:
        print(f"Octopus API error: {e}", file=sys.stderr)
        return 3
    except (PricingError, ValueError) as e:
        print(str(e), file=sys.stderr)
        return 3

    if cfg.command == "agile":
        output = format_agile_json(result) if cfg.output_format == "json" else format_agile_text(result)
    else:
        output = format_json(result) if cfg.output_format == "json" else format_text(result)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
