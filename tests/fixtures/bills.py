from datetime import date
from decimal import Decimal


def D(x) -> Decimal:
    return Decimal(str(x))


# Bill 402259109 — Octopus Tracker (December 2024 v1), 1–23 March 2026.
# (day, elec_rate, elec_kwh, elec_cost, gas_rate, gas_kwh, gas_cost)
TRACKER_MARCH = [
    (1, 18.78, 9.09, 1.71, 4.73, 36.81, 1.74),
    (2, 19.81, 7.38, 1.46, 4.73, 32.99, 1.56),
    (3, 23.27, 8.74, 2.03, 5.87, 41.41, 2.43),
    (4, 26.45, 8.08, 2.14, 6.84, 44.98, 3.08),
    (5, 25.47, 8.85, 2.25, 6.32, 49.48, 3.13),
    (6, 25.71, 11.34, 2.92, 6.53, 31.18, 2.04),
    (7, 25.25, 8.47, 2.14, 6.56, 47.38, 3.11),
    (8, 25.54, 9.82, 2.51, 6.56, 48.75, 3.20),
    (9, 27.05, 8.51, 2.30, 6.63, 39.41, 2.61),
    (10, 26.26, 6.43, 1.69, 6.88, 43.38, 2.98),
    (11, 17.74, 8.23, 1.46, 6.07, 36.38, 2.21),
    (12, 19.19, 9.20, 1.77, 6.27, 45.91, 2.88),
    (13, 18.84, 8.48, 1.60, 6.37, 41.79, 2.66),
    (14, 24.72, 6.43, 1.59, 6.36, 48.65, 3.09),
    (15, 21.82, 6.65, 1.45, 6.36, 42.94, 2.73),
    (16, 20.38, 9.04, 1.84, 6.39, 41.59, 2.66),
    (17, 22.39, 7.77, 1.74, 6.35, 35.60, 2.26),
    (18, 24.39, 11.83, 2.89, 6.44, 26.45, 1.70),
    (19, 24.85, 10.15, 2.52, 6.68, 42.86, 2.86),
    (20, 27.85, 5.28, 1.47, 7.33, 32.37, 2.37),
    (21, 26.21, 3.94, 1.03, 7.12, 33.85, 2.41),
    (22, 25.53, 8.68, 2.22, 7.12, 32.90, 2.34),
    (23, 26.09, 7.03, 1.83, 7.12, 25.82, 1.84),
]

# Tracker period totals (energy exc VAT, standing charge, VAT, total inc VAT).
TRACKER_ELEC_ENERGY_P = D(4456)   # £44.56
TRACKER_ELEC_SC_P = D(866)        # 23 days @ 37.65p = £8.66
TRACKER_ELEC_TOTAL_P = D(5588)    # £55.88
TRACKER_ELEC_SC_RATE = D("37.65")
TRACKER_GAS_ENERGY_P = D(5789)    # £57.89
TRACKER_GAS_SC_P = D(656)         # 23 days @ 28.52p = £6.56
TRACKER_GAS_TOTAL_P = D(6767)     # £67.67
TRACKER_GAS_SC_RATE = D("28.52")
TRACKER_DAYS = 23


def _march(day: int) -> date:
    return date(2026, 3, day)


def elec_daily_kwh() -> dict[date, Decimal]:
    return {_march(r[0]): D(r[2]) for r in TRACKER_MARCH}


def elec_daily_rate() -> dict[date, Decimal]:
    return {_march(r[0]): D(r[1]) for r in TRACKER_MARCH}


def gas_daily_kwh() -> dict[date, Decimal]:
    return {_march(r[0]): D(r[5]) for r in TRACKER_MARCH}


def gas_daily_rate() -> dict[date, Decimal]:
    return {_march(r[0]): D(r[4]) for r in TRACKER_MARCH}


# Flexible reference figures (Tier-2 tolerance; per-day kWh not on the bills).
# (label, total_kwh, unit_rate_exc_p, sc_rate_p, days, energy_£, total_£)
FLEXIBLE_REFERENCES = [
    ("bill1_elec_flex", D("78.0"), D("25.71"), D("43.60"), 8, D("20.07"), D("24.74")),
    ("bill1_gas_flex", D("323.7"), D("5.74"), D("32.65"), 8, D("18.59"), D("22.26")),
    ("bill2_elec", D("271.8"), D("23.71"), D("42.18"), 30, D("64.44"), D("80.94")),
    ("bill2_gas", D("849.5"), D("5.63"), D("28.06"), 30, D("47.85"), D("59.08")),
    ("bill3_elec", D("272.1"), D("23.71"), D("42.18"), 31, D("64.52"), D("81.47")),
    ("bill3_gas", D("534.7"), D("5.63"), D("28.06"), 31, D("30.12"), D("40.76")),
]

# Gas m³ → kWh references: (m3, calorific_value, expected_kwh)
GAS_CONVERSIONS = [
    (D("81.1"), D("39.2"), D("902.9")),
    (D("75.7"), D("39.5"), D("849.5")),
    (D("47.5"), D("39.6"), D("534.7")),
]
