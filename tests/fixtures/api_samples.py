ACCOUNT = {
    "number": "A-8F18337C",
    "properties": [
        {
            "electricity_meter_points": [
                {
                    "mpan": "1200033187430",
                    "is_export": False,
                    "meters": [{"serial_number": "19L3474725"}],
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

PRODUCTS_LIST = {
    "count": 1,
    "next": None,
    "results": [
        {"code": "SILVER-26-06-01", "display_name": "Octopus Tracker",
         "is_tracker": True, "brand": "OCTOPUS_ENERGY"},
    ],
}

PRODUCT_DETAIL = {
    "code": "SILVER-26-06-01",
    "single_register_electricity_tariffs": {
        "_C": {"direct_debit_monthly": {"code": "E-1R-SILVER-26-06-01-C"}},
    },
    "single_register_gas_tariffs": {
        "_C": {"direct_debit_monthly": {"code": "G-1R-SILVER-26-06-01-C"}},
    },
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
