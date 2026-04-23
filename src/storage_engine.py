"""
Battery Storage Engine for PV Systems
Models lithium-ion battery charge/discharge with round-trip efficiency,
depth-of-discharge limits, degradation curves, and cycling.
"""

import math
from dataclasses import dataclass, field
from typing import Optional, Tuple, List
import numpy as np
import pandas as pd


@dataclass
class BatterySpecs:
    """Battery Energy Storage System (BESS) Specifications."""
    capacity_kwh: float = 10.0           # Usable energy capacity (kWh)
    max_charge_kw: float = 5.0           # Max charge power (kW)
    max_discharge_kw: float = 5.0        # Max discharge power (kW)
    round_trip_efficiency: float = 0.90  # AC round-trip efficiency
    min_soc: float = 0.10                # Minimum State of Charge (10%)
    max_soc: float = 1.00                # Maximum State of Charge (100%)
    initial_soc: float = 0.50            # Starting SOC (50%)
    # Degradation (simplified Arrhenius/Wang model)
    calendar_degradation_rate: float = 0.02  # 2% per year at reference temp
    cycle_life_at_80_dod: float = 6000.0   # Cycles at 80% DoD to 80% SOH
    reference_temp_c: float = 25.0
    # Costing
    cost_per_kwh: float = 4_500_000.0    # IDR per kWh (approx lithium battery cost in Indonesia)
    replacement_threshold: float = 0.80  # Replace at 80% SOH

    @property
    def min_energy_kwh(self) -> float:
        return self.capacity_kwh * self.min_soc

    @property
    def max_energy_kwh(self) -> float:
        return self.capacity_kwh * self.max_soc

    @property
    def usable_capacity_kwh(self) -> float:
        return self.capacity_kwh * (self.max_soc - self.min_soc)

    @property
    def upfront_cost_idr(self) -> float:
        return self.capacity_kwh * self.cost_per_kwh


@dataclass
class BatteryState:
    """Hourly battery state snapshot."""
    soc: float = 0.0                     # State of Charge (0-1)
    energy_stored_kwh: float = 0.0       # Absolute energy in battery
    charge_power_kw: float = 0.0         # Charge power applied (+)
    discharge_power_kw: float = 0.0      # Discharge power applied (+)
    net_power_kw: float = 0.0            # + charge, - discharge
    throughput_kwh: float = 0.0          # Cumulative energy throughput
    temperature_c: float = 25.0          # Battery temperature estimate
    soh: float = 1.0                     # State of Health (0-1)
    cycles_equivalent: float = 0.0       # Equivalent full cycles


def simple_thermal_model(
    ambient_temp_c: float,
    prev_battery_temp_c: float,
    power_kw: float,
    thermal_time_constant_h: float = 2.0,
    internal_resistance_ohm: float = 0.01,
) -> float:
    """Simple thermal model: battery temp rises with I^2*R heating."""
    # Heuristic: heat generated ~ I^2*R, simplified to power-dependent
    heat_generation = (power_kw ** 2) * internal_resistance_ohm * 10.0  # scale factor
    # Exponential decay toward ambient
    temp = prev_battery_temp_c + (ambient_temp_c + heat_generation - prev_battery_temp_c) / thermal_time_constant_h
    return temp


def calculate_soh(
    current_soh: float,
    throughput_kwh: float,
    battery_specs: BatterySpecs,
    years_elapsed: float = 0.0,
    avg_temp_c: float = 30.0,
) -> float:
    """Calculate State of Health based on cycling and calendar aging.

    Uses a simplified two-factor degradation model:
    - Calendar: exponential decay based on time and temperature
    - Cyclic: accumulated equivalent full cycles vs. rated cycle life
    """
    # Calendar aging (Arrhenius-like)
    temp_factor = math.exp(0.0693 * (avg_temp_c - battery_specs.reference_temp_c))
    calendar_loss = battery_specs.calendar_degradation_rate * temp_factor * years_elapsed

    # Cyclic aging
    equivalent_cycles = throughput_kwh / battery_specs.capacity_kwh
    cyclic_loss = equivalent_cycles / battery_specs.cycle_life_at_80_dod

    # Combined (simplified addition, capped at 1.0)
    total_loss = calendar_loss + cyclic_loss
    soh = max(0.4, 1.0 - total_loss)  # Floor at 40% SOH
    return soh


class BatterySimulator:
    """Hourly battery charge/discharge simulator."""

    def __init__(self, specs: BatterySpecs):
        self.specs = specs
        self.state_history: List[BatteryState] = []
        self._state = BatteryState(
            soc=specs.initial_soc,
            energy_stored_kwh=specs.capacity_kwh * specs.initial_soc,
            soh=1.0,
        )

    def reset(self):
        """Reset simulator to initial conditions."""
        self._state = BatteryState(
            soc=self.specs.initial_soc,
            energy_stored_kwh=self.specs.capacity_kwh * self.specs.initial_soc,
            soh=1.0,
        )
        self.state_history = []

    @property
    def current_state(self) -> BatteryState:
        return self._state

    def step(
        self,
        power_setpoint_kw: float,
        ambient_temp_c: float = 30.0,
        dt_hours: float = 1.0,
    ) -> BatteryState:
        """Execute one simulation timestep.

        power_setpoint_kw > 0 : charge the battery
        power_setpoint_kw < 0 : discharge the battery
        Returns the actual power applied (clipped by SOC limits).
        """
        specs = self.specs
        state = self._state

        # Apply SOH to effective capacity
        effective_capacity = specs.capacity_kwh * state.soh
        min_energy = effective_capacity * specs.min_soc
        max_energy = effective_capacity * specs.max_soc

        # Clip setpoint by power limits
        max_charge = min(specs.max_charge_kw, (max_energy - state.energy_stored_kwh) / dt_hours / specs.round_trip_efficiency)
        max_discharge = min(specs.max_discharge_kw, (state.energy_stored_kwh - min_energy) / dt_hours * specs.round_trip_efficiency)

        if power_setpoint_kw > 0:
            # Requesting charge
            actual_power = min(power_setpoint_kw, max(max_charge, 0))
            # Energy into battery after inverter/charger losses
            energy_in = actual_power * specs.round_trip_efficiency * dt_hours
            new_energy = min(state.energy_stored_kwh + energy_in, max_energy)
        elif power_setpoint_kw < 0:
            # Requesting discharge
            actual_power = -min(abs(power_setpoint_kw), max(max_discharge, 0))
            energy_out = abs(actual_power) / specs.round_trip_efficiency * dt_hours
            new_energy = max(state.energy_stored_kwh - energy_out, min_energy)
        else:
            actual_power = 0.0
            new_energy = state.energy_stored_kwh

        # Update throughput
        delta_energy = abs(new_energy - state.energy_stored_kwh)
        throughput = state.throughput_kwh + delta_energy

        # Temperature estimate
        new_temp = simple_thermal_model(ambient_temp_c, state.temperature_c, actual_power)

        # Update SOH (simplified - yearly update usually enough, here hourly approx)
        years = len(self.state_history) / 8760.0
        new_soh = calculate_soh(
            state.soh, throughput, specs,
            years_elapsed=years, avg_temp_c=new_temp
        )

        new_soc = new_energy / effective_capacity if effective_capacity > 0 else 0

        cycles = throughput / effective_capacity if effective_capacity > 0 else 0

        state = BatteryState(
            soc=new_soc,
            energy_stored_kwh=new_energy,
            charge_power_kw=max(actual_power, 0),
            discharge_power_kw=max(-actual_power, 0),
            net_power_kw=actual_power,
            throughput_kwh=throughput,
            temperature_c=new_temp,
            soh=new_soh,
            cycles_equivalent=cycles,
        )
        self._state = state
        self.state_history.append(state)
        return state

    def simulate_year(
        self,
        power_setpoints_kw: pd.Series,
        ambient_temps_c: Optional[pd.Series] = None,
    ) -> pd.DataFrame:
        """Run annual simulation given hourly power setpoints."""
        self.reset()
        records = []
        for i, setpoint in enumerate(power_setpoints_kw):
            temp = ambient_temps_c.iloc[i] if ambient_temps_c is not None else 30.0
            st = self.step(setpoint, ambient_temp_c=temp)
            records.append({
                "soc": st.soc,
                "energy_stored_kwh": st.energy_stored_kwh,
                "net_power_kw": st.net_power_kw,
                "charge_power_kw": st.charge_power_kw,
                "discharge_power_kw": st.discharge_power_kw,
                "temperature_c": st.temperature_c,
                "soh": st.soh,
                "cycles_equivalent": st.cycles_equivalent,
            })
        df = pd.DataFrame(records, index=power_setpoints_kw.index)
        return df

    def get_summary(self) -> dict:
        """Return summary statistics of the simulation."""
        if not self.state_history:
            return {}
        return {
            "final_soc": self._state.soc,
            "final_soh": self._state.soh,
            "total_throughput_kwh": self._state.throughput_kwh,
            "total_cycles": self._state.cycles_equivalent,
            "avg_soc": np.mean([s.soc for s in self.state_history]),
            "min_soc": min([s.soc for s in self.state_history]),
            "max_soc": max([s.soc for s in self.state_history]),
        }
