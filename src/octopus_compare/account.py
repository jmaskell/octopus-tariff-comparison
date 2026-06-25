from dataclasses import dataclass
from datetime import date, datetime


@dataclass
class Agreement:
    tariff_code: str
    valid_from: date | None
    valid_to: date | None


@dataclass
class MeterPoint:
    identifier: str
    serials: list[str]
    agreements: list[Agreement]


@dataclass
class AccountInfo:
    electricity: MeterPoint
    gas: MeterPoint


def _to_date(value: str | None) -> date | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).date()


def _agreements(raw: list[dict]) -> list[Agreement]:
    return [
        Agreement(a["tariff_code"], _to_date(a.get("valid_from")), _to_date(a.get("valid_to")))
        for a in raw
    ]


def _meter_point(raw: dict, id_field: str) -> MeterPoint:
    return MeterPoint(
        identifier=raw[id_field],
        serials=[m["serial_number"] for m in raw.get("meters", [])],
        agreements=_agreements(raw.get("agreements", [])),
    )


def parse_account(payload: dict) -> AccountInfo:
    prop = payload["properties"][0]
    elec = [m for m in prop.get("electricity_meter_points", []) if not m.get("is_export")]
    gas = prop.get("gas_meter_points", [])
    return AccountInfo(
        electricity=_meter_point(elec[0], "mpan"),
        gas=_meter_point(gas[0], "mprn"),
    )


def agreements_in_window(
    agreements: list[Agreement], start: date, end: date
) -> list[Agreement]:
    result = []
    for a in agreements:
        a_from = a.valid_from or date.min
        a_to = a.valid_to or date.max
        if a_from < end and a_to > start:
            result.append(a)
    return result


def product_code_from_tariff(tariff_code: str) -> str:
    return tariff_code[5:-2]


def region_letter(tariff_code: str) -> str:
    return tariff_code[-1]


def build_tariff_code(supply: str, product_code: str, region: str) -> str:
    prefix = "E" if supply == "electricity" else "G"
    return f"{prefix}-1R-{product_code}-{region}"
