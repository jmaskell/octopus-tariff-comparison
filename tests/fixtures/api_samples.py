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
