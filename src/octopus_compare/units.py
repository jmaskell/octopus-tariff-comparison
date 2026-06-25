from decimal import Decimal

VOLUME_CORRECTION = Decimal("1.02264")
DEFAULT_CALORIFIC_VALUE = Decimal("39.5")


def m3_to_kwh(m3: Decimal, calorific_value: Decimal = DEFAULT_CALORIFIC_VALUE) -> Decimal:
    """Standard industry formula: m³ × volume correction × CV ÷ 3.6."""
    return Decimal(m3) * VOLUME_CORRECTION * Decimal(calorific_value) / Decimal("3.6")
