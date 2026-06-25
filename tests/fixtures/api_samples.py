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
