ACCOUNT = {
    "number": "A-8F18337C",
    "properties": [
        {
            "electricity_meter_points": [
                {
                    "mpan": "1200033187430",
                    "is_export": False,
                    "meters": [
                        {"serial_number": "I98A06379"},
                        {"serial_number": "19L3474725"},
                    ],
                    "agreements": [
                        {"tariff_code": "E-1R-SILVER-24-12-31-C",
                         "valid_from": "2025-01-01T00:00:00Z",
                         "valid_to": "2026-03-24T00:00:00Z"},
                        {"tariff_code": "E-1R-VAR-22-11-01-C",
                         "valid_from": "2026-03-24T00:00:00Z",
                         "valid_to": None},
                    ],
                }
            ],
            "gas_meter_points": [
                {
                    "mprn": "3260975110",
                    "meters": [{"serial_number": "E6S12825431961"}],
                    "agreements": [
                        {"tariff_code": "G-1R-SILVER-24-12-31-C",
                         "valid_from": "2025-01-01T00:00:00Z",
                         "valid_to": "2026-03-24T00:00:00Z"},
                        {"tariff_code": "G-1R-VAR-22-11-01-C",
                         "valid_from": "2026-03-24T00:00:00Z",
                         "valid_to": None},
                    ],
                }
            ],
        }
    ],
}

# Single-serial variant of ACCOUNT used in Agile pipeline tests where the fake
# client returns the same consumption rows for every serial.  Using one serial
# avoids double-counting kWh while keeping all other fields identical.
ACCOUNT_AGILE = {
    "number": "A-8F18337C",
    "properties": [
        {
            "electricity_meter_points": [
                {
                    "mpan": "1200033187430",
                    "is_export": False,
                    "meters": [
                        {"serial_number": "19L3474725"},
                    ],
                    "agreements": [
                        {"tariff_code": "E-1R-SILVER-24-12-31-C",
                         "valid_from": "2025-01-01T00:00:00Z",
                         "valid_to": "2026-03-24T00:00:00Z"},
                        {"tariff_code": "E-1R-VAR-22-11-01-C",
                         "valid_from": "2026-03-24T00:00:00Z",
                         "valid_to": None},
                    ],
                }
            ],
            "gas_meter_points": [
                {
                    "mprn": "3260975110",
                    "meters": [{"serial_number": "E6S12825431961"}],
                    "agreements": [
                        {"tariff_code": "G-1R-SILVER-24-12-31-C",
                         "valid_from": "2025-01-01T00:00:00Z",
                         "valid_to": "2026-03-24T00:00:00Z"},
                        {"tariff_code": "G-1R-VAR-22-11-01-C",
                         "valid_from": "2026-03-24T00:00:00Z",
                         "valid_to": None},
                    ],
                }
            ],
        }
    ],
}

# Tracker daily rates (one per local day); exc-VAT pence.
TRACKER_ELEC_RATES = {
    "results": [
        {"value_exc_vat": 18.78, "value_inc_vat": 19.719,
         "valid_from": "2026-03-01T00:00:00Z", "valid_to": "2026-03-02T00:00:00Z"},
        {"value_exc_vat": 19.81, "value_inc_vat": 20.80,
         "valid_from": "2026-03-02T00:00:00Z", "valid_to": "2026-03-03T00:00:00Z"},
    ]
}

# Flexible: single open-ended rate.
FLEX_ELEC_RATES = {
    "results": [
        {"value_exc_vat": 23.71, "value_inc_vat": 24.8955,
         "valid_from": "2026-04-01T00:00:00Z", "valid_to": None},
    ]
}

FLEX_ELEC_STANDING = {
    "results": [
        {"value_exc_vat": 42.18, "value_inc_vat": 44.289,
         "valid_from": "2026-04-01T00:00:00Z", "valid_to": None},
    ]
}

GAS_CONSUMPTION_M3 = {
    "results": [
        {"consumption": 3.52, "interval_start": "2026-03-01T00:00:00Z",
         "interval_end": "2026-03-02T00:00:00Z"},
        {"consumption": 3.16, "interval_start": "2026-03-02T00:00:00Z",
         "interval_end": "2026-03-03T00:00:00Z"},
    ]
}
ELEC_CONSUMPTION_KWH = {
    "results": [
        {"consumption": 9.09, "interval_start": "2026-03-01T00:00:00Z",
         "interval_end": "2026-03-02T00:00:00Z"},
    ]
}

# Half-hourly electricity consumption (kWh per half hour). Includes a peak slot
# (16:00 London) and a DST-boundary day.
HH_CONSUMPTION = {
    "results": [
        {"consumption": 0.20, "interval_start": "2026-03-01T00:00:00Z",
         "interval_end": "2026-03-01T00:30:00Z"},
        {"consumption": 0.30, "interval_start": "2026-03-01T00:30:00Z",
         "interval_end": "2026-03-01T01:00:00Z"},
        {"consumption": 0.90, "interval_start": "2026-03-01T16:00:00Z",
         "interval_end": "2026-03-01T16:30:00Z"},
        {"consumption": 0.10, "interval_start": "2026-03-01T17:00:00Z",
         "interval_end": "2026-03-01T17:30:00Z"},
    ]
}

# Tracker product details, forming a chain via available_to -> next available_from.
TRACKER_PRODUCTS = {
    "SILVER-25-04-15": {
        "code": "SILVER-25-04-15", "full_name": "Octopus Tracker April 2025 v2",
        "is_tracker": True,
        "available_from": "2025-04-15T00:00:00+01:00",
        "available_to": "2025-09-02T00:00:00+01:00",
    },
    "SILVER-25-09-02": {
        "code": "SILVER-25-09-02", "full_name": "Octopus Tracker September 2025 v1",
        "is_tracker": True,
        "available_from": "2025-09-02T00:00:00+01:00",
        "available_to": "2026-04-01T00:00:00+01:00",
    },
    "SILVER-26-04-01": {
        "code": "SILVER-26-04-01", "full_name": "Octopus Tracker April 2026 v1",
        "is_tracker": True,
        "available_from": "2026-04-01T00:00:00+01:00",
        "available_to": None,
    },
}


# Two-month consumption spanning a month boundary (Mar 30, 31 -> Apr 1).
def _rows(values):
    out = []
    for day, v in values.items():
        out.append({"consumption": v,
                    "interval_start": f"{day}T00:00:00Z",
                    "interval_end": f"{day}T23:30:00Z"})
    return out


ELEC_TWO_MONTH = _rows({"2026-03-30": 9.0, "2026-03-31": 9.0, "2026-04-01": 9.0})
GAS_TWO_MONTH = _rows({"2026-03-30": 30.0, "2026-03-31": 30.0, "2026-04-01": 30.0})

# Listing payload for resolve_agile_versions (GET /products/?brand=OCTOPUS_ENERGY).
AGILE_PRODUCTS_LIST = [
    {"code": "AGILE-24-10-01", "full_name": "Agile Octopus October 2024 v1",
     "display_name": "Agile Octopus",
     "available_from": "2024-10-01T00:00:00+01:00", "available_to": None},
    {"code": "AGILE-23-12-06", "full_name": "Agile Octopus December 2023 v1",
     "display_name": "Agile Octopus",
     "available_from": "2023-12-06T00:00:00Z", "available_to": "2024-10-01T00:00:00+01:00"},
    {"code": "OE-FIX-12M-26-06-24", "full_name": "Octopus 12M Fixed June 2026 v5",
     "display_name": "Octopus 12M Fixed",
     "available_from": "2026-06-24T00:00:00+01:00", "available_to": None},
]

# Listing payload for resolve_fixed (GET /products/?brand=OCTOPUS_ENERGY).
FIXED_PRODUCTS_LIST = [
    {"code": "OE-FIX-12M-26-06-24", "full_name": "Octopus 12M Fixed June 2026 v5",
     "display_name": "Octopus 12M Fixed",
     "available_from": "2026-06-24T00:00:00+01:00", "available_to": None},
    {"code": "COSY-FIX-12M-26-06-25", "full_name": "Cosy Octopus 12M Fixed",
     "display_name": "Cosy", "available_from": "2026-06-25T00:00:00+01:00", "available_to": None},
]
