"""
Canonical PV simulation engine.

Single source of truth for `simulate_pv_system`. The module is consumed by:
  - gui.py (Streamlit UI)
  - src/pv_agents.py (CalculationEngine.simulate_annual_production)
  - src/pv_agents_cloud.py (CalculationEngine.simulate_annual_production)

Replaces three near-duplicate implementations that had drifted in subtle ways
(temperature coefficient, performance-ratio formula, gamma_pdc handling).

Physics:
  - Sky-diffuse transposition: pvlib Hay-Davies
  - Cell temperature: pvlib SAPM open-rack glass-glass
  - Optical (IAM): pvlib ASHRAE on the beam component
  - DC: PVWatts-style with gamma_pdc temperature derate
  - AC: flat inverter efficiency with hard clip to AC nameplate
  - System losses: documented LossModel applied as a single multiplier
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

import numpy as np
import pandas as pd
from pvlib import iam, irradiance, location, temperature


@dataclass
class LossModel:
    """System loss components, expressed as percentages (e.g. 2.0 == 2%).

    Defaults are zero so the refactor is non-behaviour-changing; consumers
    that want a realistic stack should construct an instance explicitly,
    e.g. ``LossModel.realistic()``. Literature-typical totals (PVWatts
    default) are ~12-14%.
    """
    soiling_pct: float = 0.0
    mismatch_pct: float = 0.0
    wiring_dc_pct: float = 0.0
    connections_pct: float = 0.0
    light_induced_degradation_pct: float = 0.0
    nameplate_pct: float = 0.0
    age_pct_per_year: float = 0.0
    age_years: float = 0.0

    @classmethod
    def realistic(cls) -> "LossModel":
        """Loss stack matching PVWatts defaults (~14% total)."""
        return cls(
            soiling_pct=2.0,
            mismatch_pct=2.0,
            wiring_dc_pct=2.0,
            connections_pct=0.5,
            light_induced_degradation_pct=1.5,
            nameplate_pct=1.0,
        )

    def total_derate(self) -> float:
        """Combined multiplicative derate factor in [0, 1]."""
        components_pct = (
            self.soiling_pct
            + self.mismatch_pct
            + self.wiring_dc_pct
            + self.connections_pct
            + self.light_induced_degradation_pct
            + self.nameplate_pct
            + self.age_pct_per_year * self.age_years
        )
        return max(0.0, 1.0 - components_pct / 100.0)


# Open-rack glass-glass module mounting from pvlib's SAPM parameter set.
_SAPM_OPEN_RACK = temperature.TEMPERATURE_MODEL_PARAMETERS["sapm"][
    "open_rack_glass_glass"
]


def _build_simulation(
    *,
    latitude: float,
    longitude: float,
    altitude: float,
    timezone: str,
    tilt: float,
    azimuth: float,
    dc_capacity_kw: float,
    gamma_pdc: float,
    inverter_efficiency: float,
    ac_capacity_kw: float,
    weather: pd.DataFrame,
    losses: LossModel,
) -> Dict:
    """Run the core annual simulation. Returns hourly_ac, poa_global, dc_capacity."""
    loc = location.Location(latitude, longitude, altitude=altitude, tz=timezone)
    solar_pos = loc.get_solarposition(weather.index)
    dni_extra = irradiance.get_extra_radiation(weather.index)

    poa = irradiance.get_total_irradiance(
        tilt,
        azimuth,
        solar_pos["zenith"],
        solar_pos["azimuth"],
        weather["dni"].fillna(0),
        weather["ghi"].fillna(0),
        weather["dhi"].fillna(0),
        dni_extra=dni_extra,
        model="haydavies",
    )

    aoi = irradiance.aoi(tilt, azimuth, solar_pos["zenith"], solar_pos["azimuth"])
    iam_beam = iam.ashrae(aoi)
    poa_effective = (
        poa["poa_direct"].fillna(0) * iam_beam.fillna(0)
        + poa["poa_diffuse"].fillna(0)
    ).clip(lower=0)

    wind_speed = weather["wind_speed"].fillna(1.0) if "wind_speed" in weather else 1.0
    temp_cell = temperature.sapm_cell(
        poa_effective,
        weather["temp_air"].fillna(20.0),
        wind_speed,
        a=_SAPM_OPEN_RACK["a"],
        b=_SAPM_OPEN_RACK["b"],
        deltaT=_SAPM_OPEN_RACK["deltaT"],
    )

    dc_power = (
        dc_capacity_kw
        * (poa_effective / 1000.0)
        * (1.0 + gamma_pdc * (temp_cell - 25.0))
        * losses.total_derate()
    ).clip(lower=0)

    ac_power = (dc_power * inverter_efficiency).clip(upper=ac_capacity_kw)
    hourly_ac = ac_power.fillna(0)

    return {
        "hourly_ac": hourly_ac,
        "poa_global": poa["poa_global"].fillna(0),
        "dc_capacity_kw": dc_capacity_kw,
        "ac_capacity_kw": ac_capacity_kw,
    }


def simulate_pv_system(specs: Dict, weather: pd.DataFrame) -> Dict:
    """Adapter matching the legacy gui.simulate_pv_system signature.

    Inputs
    ------
    specs : dict with latitude, longitude, altitude, timezone, tilt, azimuth,
            system_capacity_kw, module_power, gamma_pdc, inverter_efficiency,
            cost_per_watt, electricity_rate, optional ac_capacity_kw, losses.
    weather : DataFrame indexed by tz-aware timestamps with columns
              ghi, dni, dhi, temp_air, wind_speed.
    """
    latitude = specs["latitude"]
    longitude = specs["longitude"]
    altitude = specs.get("altitude", 0)
    timezone = specs.get("timezone", "Asia/Jakarta")
    tilt = specs.get("tilt", abs(latitude))
    azimuth = specs.get("azimuth", 0)
    system_capacity_kw = specs.get("system_capacity_kw", 10.0)

    module_power = specs.get("module_power", 450)
    gamma_pdc = specs.get("gamma_pdc", -0.0035)
    inverter_efficiency = specs.get("inverter_efficiency", 0.96)

    num_modules = int(np.ceil(system_capacity_kw * 1000 / module_power))
    actual_capacity_kw = num_modules * module_power / 1000
    ac_capacity_kw = specs.get("ac_capacity_kw", actual_capacity_kw * 0.9)

    losses = specs.get("losses") or LossModel()

    sim = _build_simulation(
        latitude=latitude,
        longitude=longitude,
        altitude=altitude,
        timezone=timezone,
        tilt=tilt,
        azimuth=azimuth,
        dc_capacity_kw=actual_capacity_kw,
        gamma_pdc=gamma_pdc,
        inverter_efficiency=inverter_efficiency,
        ac_capacity_kw=ac_capacity_kw,
        weather=weather,
        losses=losses,
    )

    hourly_ac = sim["hourly_ac"]
    poa_global = sim["poa_global"]
    annual_kwh = float(hourly_ac.sum())

    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    monthly = {
        month_names[i - 1]: float(hourly_ac[hourly_ac.index.month == i].sum())
        for i in range(1, 13)
    }

    specific_yield = annual_kwh / actual_capacity_kw if actual_capacity_kw > 0 else 0.0
    capacity_factor = (
        annual_kwh / (actual_capacity_kw * 8760) * 100 if actual_capacity_kw > 0 else 0.0
    )
    poa_kwh_per_m2 = float(poa_global.sum()) / 1000.0
    pr_denominator = poa_kwh_per_m2 * actual_capacity_kw
    performance_ratio = (annual_kwh / pr_denominator * 100) if pr_denominator > 0 else 0.0

    cost_per_watt = specs.get("cost_per_watt", 2.50)
    electricity_rate = specs.get("electricity_rate", 0.13)
    system_cost = actual_capacity_kw * 1000 * cost_per_watt
    annual_savings = annual_kwh * electricity_rate
    payback = system_cost / annual_savings if annual_savings > 0 else float("inf")
    lcoe = system_cost / (annual_kwh * 25) if annual_kwh > 0 else float("inf")

    return {
        "annual_kwh": annual_kwh,
        "specific_yield": specific_yield,
        "capacity_factor": capacity_factor,
        "performance_ratio": performance_ratio,
        "monthly_kwh": monthly,
        "peak_power_kw": float(hourly_ac.max()),
        "dc_capacity_kw": actual_capacity_kw,
        "ac_capacity_kw": ac_capacity_kw,
        "num_modules": num_modules,
        "system_cost": system_cost,
        "annual_savings": annual_savings,
        "payback_years": payback,
        "lcoe": lcoe,
        "hourly_output": hourly_ac,
        "poa_global": poa_global,
    }
