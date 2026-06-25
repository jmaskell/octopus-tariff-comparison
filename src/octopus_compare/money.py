from decimal import Decimal, ROUND_HALF_UP

PENNY = Decimal("1")
VAT_RATE = Decimal("0.05")


def round_pence(value: Decimal) -> Decimal:
    return value.quantize(PENNY, rounding=ROUND_HALF_UP)


def vat_pence(subtotal_pence: Decimal) -> Decimal:
    return round_pence(subtotal_pence * VAT_RATE)


def pounds(pence: Decimal) -> Decimal:
    return (pence / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
