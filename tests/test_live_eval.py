import os
from datetime import date
from decimal import Decimal

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("OCTOPUS_LIVE_EVAL") != "1",
    reason="set OCTOPUS_LIVE_EVAL=1 (needs real OCTOPUS_API_KEY) to run",
)


@pytest.mark.parametrize(
    "period_from, period_to, expected_elec_total, expected_gas_total",
    [
        # Bill 411480086 (April 2026, all Flexible).
        (date(2026, 4, 1), date(2026, 5, 1), Decimal("80.94"), Decimal("59.08")),
        # Bill 420492378 (May 2026, all Flexible).
        (date(2026, 5, 1), date(2026, 6, 1), Decimal("81.47"), Decimal("40.76")),
    ],
)
def test_actual_totals_match_bills(period_from, period_to,
                                   expected_elec_total, expected_gas_total):
    from dotenv import dotenv_values
    from octopus_compare.client import OctopusClient
    from octopus_compare.config import Config
    from octopus_compare.pipeline import run_comparison

    env = {**dotenv_values(".env"), **os.environ}
    cfg = Config(
        api_key=env["OCTOPUS_API_KEY"], account=env["OCTOPUS_ACCOUNT"],
        period_from=period_from, period_to=period_to,
        output_format="text", gas_calorific_value=Decimal("39.5"),
        gas_units="auto", verbose=True,
    )
    result = run_comparison(OctopusClient(cfg.api_key), cfg)
    # Actual (Flexible) side should reproduce the bill within a few pence.
    assert abs(result.elec_actual.total_pounds - expected_elec_total) <= Decimal("0.50")
    assert abs(result.gas_actual.total_pounds - expected_gas_total) <= Decimal("1.00")
