from decimal import Decimal

from octopus_compare.verdict import Verdict, decide


def test_clear_switch_when_challenger_well_below():
    assert decide(Decimal("1000"), Decimal("950")) == Verdict.SWITCH


def test_clear_stay_when_status_quo_well_below():
    assert decide(Decimal("950"), Decimal("1000")) == Verdict.STAY


def test_too_close_when_gap_under_abs_floor():
    # £0.50 gap, well over 2% would need £19 — fails abs floor anyway
    assert decide(Decimal("1080.00"), Decimal("1080.50")) == Verdict.TOO_CLOSE


def test_too_close_when_gap_over_fiver_but_under_two_pct():
    # £8 gap on ~£812 is 0.99% < 2% -> too close despite clearing £5
    assert decide(Decimal("812"), Decimal("820")) == Verdict.TOO_CLOSE


def test_switch_needs_both_pct_and_abs():
    # £40 on £1000 = 4% and > £5 -> clear
    assert decide(Decimal("1040"), Decimal("1000")) == Verdict.SWITCH


def test_small_bill_blocked_by_abs_floor():
    # £4 gap on £100 = 4% (clears pct) but < £5 -> too close
    assert decide(Decimal("104"), Decimal("100")) == Verdict.TOO_CLOSE
