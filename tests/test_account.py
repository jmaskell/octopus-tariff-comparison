from datetime import date

from octopus_compare.account import (
    parse_account,
    agreements_in_window,
    product_code_from_tariff,
    Agreement,
)
from tests.fixtures.api_samples import ACCOUNT


def test_parse_account_extracts_meter_points():
    info = parse_account(ACCOUNT)
    assert info.electricity.identifier == "1200033187430"
    assert info.electricity.serial == "19L3474725"
    assert info.gas.identifier == "3260975110"
    assert info.gas.serial == "E6S12825431961"
    assert len(info.electricity.agreements) == 2


def test_product_code_from_tariff():
    assert product_code_from_tariff("E-1R-VAR-22-11-01-C") == "VAR-22-11-01"
    assert product_code_from_tariff("G-1R-SILVER-24-12-31-C") == "SILVER-24-12-31"


def test_agreements_in_window_overlap():
    info = parse_account(ACCOUNT)
    win = agreements_in_window(info.electricity.agreements,
                               date(2026, 4, 1), date(2026, 5, 1))
    assert [a.tariff_code for a in win] == ["E-1R-VAR-22-11-01-C"]

    spanning = agreements_in_window(info.electricity.agreements,
                                    date(2026, 3, 1), date(2026, 4, 1))
    assert {a.tariff_code for a in spanning} == {
        "E-1R-SILVER-24-12-31-C", "E-1R-VAR-22-11-01-C"}
