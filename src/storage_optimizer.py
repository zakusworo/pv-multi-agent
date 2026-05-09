"""
Self-Consumption Optimizer for Grid-Tied PV + Battery Systems.

Manages hourly energy flows:
    Solar Generation -> [Battery] -> [Load] -> [Grid Export]
    Grid Import -> [Battery] -> [Load]

Strategy: maximize self-consumption (solar powers load first, then charges battery,
only exports excess; battery discharges to cover load when solar < load).
"""

from dataclasses import dataclass, field
from typing import Dict, Optional
import pandas as pd
import numpy as np

try:
    from .storage_engine import BatterySimulator, BatterySpecs
    from .load_profiles import generate_profile
    from .pln_tariffs import get_tariff, calculate_bill_components
except ImportError:
    from storage_engine import BatterySimulator, BatterySpecs
    from load_profiles import generate_profile
    from pln_tariffs import get_tariff, calculate_bill_components


@dataclass
class StorageScenario:
    """User scenario for storage simulation."""
    system_capacity_kw: float = 5.0
    battery_specs: BatterySpecs = field(default_factory=BatterySpecs)
    profile_type: str = "residential"
    annual_load_kwh: Optional[float] = None
    tariff_code: str = "R-1/2200VA"
    # Grid limits
    max_grid_import_kw: float = 10.0
    max_grid_export_kw: float = 10.0


@dataclass
class HourlyFlow:
    """Energy flow for one hour (all values in kWh for that hour)."""
    solar_generation: float = 0.0
    load_consumption: float = 0.0
    battery_charge: float = 0.0
    battery_discharge: float = 0.0
    grid_import: float = 0.0
    grid_export: float = 0.0
    self_consumed: float = 0.0       # solar directly + battery->load
    battery_soc: float = 0.0
    unmet_load: float = 0.0


@dataclass
class AnnualStorageResult:
    """Complete annual self-consumption simulation results."""
    scenario: StorageScenario
    hourly_flows: pd.DataFrame = field(default_factory=pd.DataFrame)
    # Aggregates
    total_solar_kwh: float = 0.0
    total_load_kwh: float = 0.0
    total_self_consumed_kwh: float = 0.0
    total_battery_charge_kwh: float = 0.0
    total_battery_discharge_kwh: float = 0.0
    total_grid_import_kwh: float = 0.0
    total_grid_export_kwh: float = 0.0
    self_consumption_ratio: float = 0.0  # solar used on-site / total solar
    self_sufficiency_ratio: float = 0.0  # load met on-site / total load
    # Financials
    total_bill_without_pv_idr: float = 0.0
    total_bill_with_pv_idr: float = 0.0
    annual_savings_idr: float = 0.0
    payback_years: float = 0.0
    # Battery
    battery_summary: Dict = field(default_factory=dict)


def self_consumption_optimizer(
    solar_generation_kw: pd.Series,
    load_kw: pd.Series,
    battery_specs: BatterySpecs,
    tariff_code: str = "R-1/2200VA",
    strategy: str = "self_consumption_first",
) -> AnnualStorageResult:
    """Optimize self-consumption with battery storage.

    Strategy:
        1. Solar meets load directly.
        2. Excess solar charges battery (up to max charge rate).
        3. Any remaining solar exports to grid.
        4. If load > solar, battery discharges to cover gap (up to max discharge).
        5. Any remaining shortfall imports from grid.

    Args:
        solar_generation_kw: Hourly solar output (kW ≈ kWh for timestep)
        load_kw: Hourly load (kW ≈ kWh for timestep)
        battery_specs: Battery storage specifications
        tariff_code: PLN tariff for financial calculations
        strategy: Currently only 'self_consumption_first' supported

    Returns:
        AnnualStorageResult with complete flow data.
    """
    if len(solar_generation_kw) != len(load_kw):
        raise ValueError("solar_generation and load must have same length")

    n_hours = len(solar_generation_kw)
    times = solar_generation_kw.index

    sim = BatterySimulator(battery_specs)
    sim.reset()

    flows = []
    for i in range(n_hours):
        solar = max(0.0, float(solar_generation_kw.iloc[i]))
        load = max(0.0, float(load_kw.iloc[i]))

        # Step 1: Solar meets load directly
        solar_to_load = min(solar, load)
        solar_remaining = solar - solar_to_load
        load_remaining = load - solar_to_load

        battery_charge = 0.0
        battery_discharge = 0.0
        grid_export = 0.0
        grid_import = 0.0
        unmet = 0.0

        if solar_remaining > 0:
            # Step 2: Excess solar charges battery
            # Power setpoint positive = charge
            st = sim.step(solar_remaining, ambient_temp_c=30.0)
            actual_charge = st.charge_power_kw  # <= solar_remaining
            battery_charge = actual_charge
            # Any solar that couldn't be stored (battery full or rate limit)
            not_charged = solar_remaining - actual_charge
            if not_charged > 0:
                grid_export = not_charged

        if load_remaining > 0:
            # Step 4: Battery discharges to cover gap
            st = sim.step(-load_remaining, ambient_temp_c=30.0)
            actual_discharge = st.discharge_power_kw
            battery_discharge = actual_discharge
            # Any load not met by battery: import from grid
            still_unmet = load_remaining - actual_discharge
            if still_unmet > 0:
                grid_import = still_unmet
                unmet = still_unmet

        # Update SOC from current state
        current_soc = sim.current_state.soc

        self_consumed = solar_to_load + battery_discharge

        flows.append(HourlyFlow(
            solar_generation=solar,
            load_consumption=load,
            battery_charge=battery_charge,
            battery_discharge=battery_discharge,
            grid_import=grid_import,
            grid_export=grid_export,
            self_consumed=self_consumed,
            battery_soc=current_soc,
            unmet_load=unmet,
        ))

    # Build DataFrame
    df = pd.DataFrame([
        {
            "solar_generation": f.solar_generation,
            "load_consumption": f.load_consumption,
            "battery_charge": f.battery_charge,
            "battery_discharge": f.battery_discharge,
            "grid_import": f.grid_import,
            "grid_export": f.grid_export,
            "self_consumed": f.self_consumed,
            "battery_soc": f.battery_soc,
            "unmet_load": f.unmet_load,
        }
        for f in flows
    ], index=times)

    # Aggregations
    total_solar = df["solar_generation"].sum()
    total_load = df["load_consumption"].sum()
    total_self = df["self_consumed"].sum()
    total_batt_charge = df["battery_charge"].sum()
    total_batt_disch = df["battery_discharge"].sum()
    total_import = df["grid_import"].sum()
    total_export = df["grid_export"].sum()

    sc_ratio = (total_self / total_solar) if total_solar > 0 else 0.0
    ss_ratio = (total_self / total_load) if total_load > 0 else 0.0

    # Financials (input series is assumed to span a full year)
    tariff = get_tariff(tariff_code)
    bill_without_pv = calculate_bill_components(total_load, 0.0, tariff)["net_bill_idr"]
    bill_with_pv = calculate_bill_components(total_import, total_export, tariff)["net_bill_idr"]
    savings = bill_without_pv - bill_with_pv

    # Simple payback: only battery cost (PV cost assumed sunk or separate)
    battery_cost = battery_specs.upfront_cost_idr

    result = AnnualStorageResult(
        scenario=StorageScenario(
            system_capacity_kw=0.0,  # filled externally
            battery_specs=battery_specs,
            tariff_code=tariff_code,
        ),
        hourly_flows=df,
        total_solar_kwh=total_solar,
        total_load_kwh=total_load,
        total_self_consumed_kwh=total_self,
        total_battery_charge_kwh=total_batt_charge,
        total_battery_discharge_kwh=total_batt_disch,
        total_grid_import_kwh=total_import,
        total_grid_export_kwh=total_export,
        self_consumption_ratio=sc_ratio,
        self_sufficiency_ratio=ss_ratio,
        total_bill_without_pv_idr=bill_without_pv,
        total_bill_with_pv_idr=bill_with_pv,
        annual_savings_idr=savings,
        payback_years=(battery_cost / savings) if savings > 0 else float("inf"),
        battery_summary=sim.get_summary(),
    )
    return result
