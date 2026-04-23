"""
PLN (Perusahaan Listrik Negara) Tariff Data + Net Metering Rules
Based on PLN tariff regulations for on-grid PV Net Metering (NEB)

Reference: PLN Tariff Adjustment 2024 and MEMR Regulation No. 26/2021
on Rooftop Solar PV Net Metering.
"""

from dataclasses import dataclass
from typing import Dict, Optional
import pandas as pd


@dataclass
class PLNTariff:
    """PLN electricity tariff tier."""
    name: str                           # e.g. "R-1/1300VA"
    customer_group: str                 # "R-1", "B-2", "I-3", etc.
    power_va: int                       # Connected power (VA)
    energy_rate_idr_kwh: float          # IDR per kWh (varies by block)
    fixed_charge_idr_month: float = 0.0  # Monthly fixed charge
    demand_charge_idr_kva_month: float = 0.0  # Demand charge per kVA (for B, I)
    # Time-of-use (if applicable)
    peak_rate_idr_kwh: Optional[float] = None
    off_peak_rate_idr_kwh: Optional[float] = None


# PLN Tariff Blocks (simplified average — actual PLN has progressive blocks)
# As of 2024 approximately, in IDR/kWh, subject to periodic adjustment
PLN_TARIFFS: Dict[str, PLNTariff] = {
    # Residential — R-1 (Rumah Tangga)
    "R-1/450VA": PLNTariff(
        name="R-1/450VA",
        customer_group="R-1",
        power_va=450,
        energy_rate_idr_kwh=415,  # Subsidized
        fixed_charge_idr_month=11_000,
    ),
    "R-1/900VA": PLNTariff(
        name="R-1/900VA",
        customer_group="R-1",
        power_va=900,
        energy_rate_idr_kwh=1_352,
        fixed_charge_idr_month=40_000,
    ),
    "R-1/1300VA": PLNTariff(
        name="R-1/1300VA",
        customer_group="R-1",
        power_va=1300,
        energy_rate_idr_kwh=1_467,
        fixed_charge_idr_month=52_000,
    ),
    "R-1/2200VA": PLNTariff(
        name="R-1/2200VA",
        customer_group="R-1",
        power_va=2200,
        energy_rate_idr_kwh=1_467,
        fixed_charge_idr_month=73_000,
    ),
    "R-1/3500VA": PLNTariff(
        name="R-1/3500VA",
        customer_group="R-1",
        power_va=3500,
        energy_rate_idr_kwh=1_467,
        fixed_charge_idr_month=113_000,
    ),
    # R-2 (Rumah Tangga > 3500VA up to 14 kVA)
    "R-2": PLNTariff(
        name="R-2",
        customer_group="R-2",
        power_va=5500,
        energy_rate_idr_kwh=1_467,
        fixed_charge_idr_month=163_000,
    ),
    # R-3 (Rumah Tangga > 14 kVA)
    "R-3": PLNTariff(
        name="R-3",
        customer_group="R-3",
        power_va=16500,
        energy_rate_idr_kwh=1_467,
        fixed_charge_idr_month=300_000,
    ),
    # Commercial — B-2 (Bisnis 6.6 kVA - 200 kVA)
    "B-2": PLNTariff(
        name="B-2",
        customer_group="B-2",
        power_va=66000,
        energy_rate_idr_kwh=1_445,
        fixed_charge_idr_month=75_000 * 10,  # scaled placeholder
        demand_charge_idr_kva_month=45_000,
    ),
    # Industrial — I-3 (Industri > 200 kVA)
    "I-3": PLNTariff(
        name="I-3",
        customer_group="I-3",
        power_va=200000,
        energy_rate_idr_kwh=996,  # LPB + variable, approximated
        fixed_charge_idr_month=3_000_000,
        demand_charge_idr_kva_month=38_000,
    ),
}


def get_tariff(tariff_code: str) -> PLNTariff:
    """Get tariff by code."""
    if tariff_code not in PLN_TARIFFS:
        raise ValueError(f"Unknown tariff code: {tariff_code}. Available: {list(PLN_TARIFFS.keys())}")
    return PLN_TARIFFS[tariff_code]


def list_tariffs() -> pd.DataFrame:
    """Return all tariffs as a DataFrame."""
    rows = []
    for code, t in PLN_TARIFFS.items():
        rows.append({
            "code": code,
            "group": t.customer_group,
            "power_va": t.power_va,
            "energy_idr_kwh": t.energy_rate_idr_kwh,
            "fixed_idr_month": t.fixed_charge_idr_month,
            "demand_idr_kva_month": t.demand_charge_idr_kva_month,
        })
    return pd.DataFrame(rows)


# Net Metering (NEB) Rules
# Export value = ~75-100% of import rate (varies by regulation period)
NET_METERING_EXPORT_RATE_FACTOR = 0.75  # Simplified — check current MEMR regulation


def calculate_net_metering_credit(
    export_kwh: float,
    import_rate_idr_kwh: float,
    factor: float = NET_METERING_EXPORT_RATE_FACTOR,
) -> float:
    """Calculate export credit for net metering.

    Returns credit amount in IDR.
    """
    return export_kwh * import_rate_idr_kwh * factor


def calculate_bill_components(
    import_kwh: float,
    export_kwh: float,
    tariff: PLNTariff,
    peak_demand_kva: float = 0.0,
) -> Dict[str, float]:
    """Calculate monthly PLN bill components.

    Args:
        import_kwh: Energy drawn from grid (kWh)
        export_kwh: Energy exported to grid (kWh)
        tariff: PLNTariff object
        peak_demand_kva: Peak apparent power demand (for B-2, I-3)

    Returns:
        Dict with total_bill_idr, energy_charge, export_credit, net_bill_idr, etc.
    """
    energy_charge = import_kwh * tariff.energy_rate_idr_kwh
    demand_charge = peak_demand_kva * tariff.demand_charge_idr_kva_month
    fixed_charge = tariff.fixed_charge_idr_month

    export_credit = calculate_net_metering_credit(export_kwh, tariff.energy_rate_idr_kwh)

    net_bill = energy_charge + demand_charge + fixed_charge - export_credit
    net_bill = max(0, net_bill)  # Can't go negative in simple model

    return {
        "import_kwh": import_kwh,
        "export_kwh": export_kwh,
        "energy_charge_idr": energy_charge,
        "demand_charge_idr": demand_charge,
        "fixed_charge_idr": fixed_charge,
        "export_credit_idr": export_credit,
        "net_bill_idr": net_bill,
        "savings_from_self_consumption_idr": export_kwh * tariff.energy_rate_idr_kwh * (1 - NET_METERING_EXPORT_RATE_FACTOR),
    }
