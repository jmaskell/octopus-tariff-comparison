from decimal import Decimal

from octopus_compare.money import round_pence, vat_pence, pounds, VAT_RATE


def test_round_pence_half_up():
    assert round_pence(Decimal("865.95")) == Decimal("866")
    assert round_pence(Decimal("291.5514")) == Decimal("292")
    assert round_pence(Decimal("170.71")) == Decimal("171")


def test_vat_is_five_percent():
    assert VAT_RATE == Decimal("0.05")
    assert vat_pence(Decimal("5322")) == Decimal("266")   # bill 1 elec tracker
    assert vat_pence(Decimal("6445")) == Decimal("322")   # bill 1 gas tracker


def test_pounds_two_dp():
    assert pounds(Decimal("5588")) == Decimal("55.88")
