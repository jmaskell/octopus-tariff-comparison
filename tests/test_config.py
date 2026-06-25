from datetime import date
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
