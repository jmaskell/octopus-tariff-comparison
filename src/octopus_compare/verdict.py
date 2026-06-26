from decimal import Decimal
from enum import Enum


class Verdict(str, Enum):
    STAY = "STAY"
    SWITCH = "SWITCH"
    TOO_CLOSE = "TOO_CLOSE"


def decide(
    status_quo: Decimal,
    challenger: Decimal,
    pct: Decimal = Decimal("2"),
    abs_pounds: Decimal = Decimal("5"),
) -> Verdict:
    """Compare a challenger total against the status-quo total.

    The challenger 'wins' (SWITCH) only if it is cheaper by more than `pct`%
    of the cheaper of the two AND by more than `abs_pounds`. Symmetrically the
    status quo 'wins' (STAY). Anything inside the band is TOO_CLOSE.
    """
    gap = status_quo - challenger  # >0 => challenger cheaper
    cheaper = min(status_quo, challenger)
    clear = abs(gap) > (pct / 100 * cheaper) and abs(gap) > abs_pounds
    if not clear:
        return Verdict.TOO_CLOSE
    return Verdict.SWITCH if gap > 0 else Verdict.STAY
