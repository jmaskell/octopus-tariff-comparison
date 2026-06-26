from datetime import date, time
from decimal import Decimal

import pytest

from octopus_compare.config import load_config, Config, ConfigError

ENV = {"OCTOPUS_API_KEY": "sk_test", "OCTOPUS_ACCOUNT": "A-8F18337C"}
TODAY = date(2026, 6, 25)


def test_defaults_three_months():
    cfg = load_config([], ENV, TODAY)
    assert isinstance(cfg, Config)
    assert cfg.api_key == "sk_test"
    assert cfg.account == "A-8F18337C"
    assert cfg.period_to == TODAY
    assert cfg.period_from == date(2026, 3, 27)  # 90 days before
    assert cfg.output_format == "text"
    assert cfg.gas_calorific_value == Decimal("39.5")
    assert cfg.gas_units == "auto"


def test_months_flag():
    cfg = load_config(["--months", "1"], ENV, TODAY)
    assert cfg.period_from == date(2026, 5, 26)  # 30 days before


def test_from_to_override():
    cfg = load_config(["--from", "2026-04-01", "--to", "2026-04-30"], ENV, TODAY)
    assert cfg.period_from == date(2026, 4, 1)
    assert cfg.period_to == date(2026, 4, 30)


def test_missing_credentials_raises():
    with pytest.raises(ConfigError):
        load_config([], {}, TODAY)


def test_tracker_product_and_region_default_none():
    cfg = load_config([], ENV, TODAY)
    assert cfg.tracker_product is None
    assert cfg.region is None


def test_tracker_product_and_region_flags():
    cfg = load_config(
        ["--tracker-product", "SILVER-26-04-01", "--region", "C"], ENV, TODAY)
    assert cfg.tracker_product == "SILVER-26-04-01"
    assert cfg.region == "C"


def test_fixed_product_default_none():
    cfg = load_config([], ENV, TODAY)
    assert cfg.fixed_product is None


def test_fixed_product_flag():
    cfg = load_config(["--fixed-product", "OE-FIX-12M-26-06-24"], ENV, TODAY)
    assert cfg.fixed_product == "OE-FIX-12M-26-06-24"


def test_no_subcommand_defaults_to_compare():
    cfg = load_config([], ENV, TODAY)
    assert cfg.command == "compare"
    assert cfg.agile_product is None
    assert cfg.peak_window == (time(16, 0), time(19, 0))


def test_agile_subcommand():
    cfg = load_config(["agile"], ENV, TODAY)
    assert cfg.command == "agile"


def test_agile_subcommand_shares_common_flags():
    cfg = load_config(["agile", "--from", "2026-01-01", "--to", "2026-05-31"],
                      ENV, TODAY)
    assert cfg.command == "agile"
    assert cfg.period_from == date(2026, 1, 1)
    assert cfg.period_to == date(2026, 5, 31)


def test_agile_product_and_peak_window_flags():
    cfg = load_config(
        ["agile", "--agile-product", "AGILE-24-10-01", "--peak-window", "17:00-20:00"],
        ENV, TODAY)
    assert cfg.agile_product == "AGILE-24-10-01"
    assert cfg.peak_window == (time(17, 0), time(20, 0))


def test_compare_flags_still_work_without_subcommand():
    cfg = load_config(["--tracker-product", "SILVER-26-04-01"], ENV, TODAY)
    assert cfg.command == "compare"
    assert cfg.tracker_product == "SILVER-26-04-01"
