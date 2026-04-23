"""
Indonesia Load Profiles for PV Self-Consumption Simulation.
Generates realistic hourly load profiles for residential (R-1/TM), 
commercial (B-2), and industrial (I-3) customers.

Load profiles are simplified based on PLN customer categories and typical
Indonesian usage patterns (tropical climate, morning/evening peaks).
"""

import numpy as np
import pandas as pd
from typing import Optional


# Typical PLN residential tariff: R-1 900VA, 1300VA, 2200VA, etc.
# R-1/1300VA avg: ~1.3-3.5 kWh/day depending on household size

_RESIDENTIAL_HOURLY_SHAPE = np.array([
    0.30, 0.25, 0.22, 0.20, 0.20, 0.25,  # 00-05
    0.45, 0.80, 0.60, 0.50, 0.45, 0.50,  # 06-11
    0.70, 0.60, 0.55, 0.60, 0.75, 1.00,  # 12-17 (afternoon AC peak)
    1.20, 1.10, 0.90, 0.70, 0.55, 0.40,  # 18-23 (evening peak)
], dtype=float)

_COMMERCIAL_HOURLY_SHAPE = np.array([
    0.10, 0.08, 0.06, 0.05, 0.05, 0.06,  # 00-05
    0.15, 0.40, 0.85, 1.00, 1.00, 0.95,  # 06-11
    0.90, 0.85, 0.85, 0.80, 0.70, 0.50,  # 12-17
    0.20, 0.12, 0.10, 0.10, 0.10, 0.10,  # 18-23
], dtype=float)

_INDUSTRIAL_HOURLY_SHAPE = np.array([
    0.55, 0.55, 0.55, 0.55, 0.55, 0.55,  # 00-05 (night shift baseline)
    0.60, 0.75, 0.90, 1.00, 1.00, 1.00,  # 06-11
    1.00, 1.00, 1.00, 0.95, 0.90, 0.80,  # 12-17
    0.70, 0.60, 0.58, 0.55, 0.55, 0.55,  # 18-23
], dtype=float)


def generate_profile(
    profile_type: str = "residential",
    annual_kwh: Optional[float] = None,
    times: Optional[pd.DatetimeIndex] = None,
    random_seed: Optional[int] = 42,
) -> pd.Series:
    """Generate hourly load profile for a full year.

    Args:
        profile_type: 'residential', 'commercial', or 'industrial'
        annual_kwh: Total annual consumption. Defaults based on type:
            residential=4380, commercial=36500, industrial=350000
        times: DatetimeIndex. Defaults to hourly for one typical year (8760h)
        random_seed: For reproducible noise

    Returns:
        pd.Series with hourly load in kW (approx, mean = kWh for that hour)
    """
    if times is None:
        times = pd.date_range("2024-01-01", periods=8760, freq="h")

    if profile_type == "residential":
        shape = _RESIDENTIAL_HOURLY_SHAPE.copy()
        if annual_kwh is None:
            annual_kwh = 4380.0  # ~12 kWh/day, typical 1300VA-2200VA home
    elif profile_type == "commercial":
        shape = _COMMERCIAL_HOURLY_SHAPE.copy()
        if annual_kwh is None:
            annual_kwh = 36500.0  # ~100 kWh/day, small office/shop
    elif profile_type == "industrial":
        shape = _INDUSTRIAL_HOURLY_SHAPE.copy()
        if annual_kwh is None:
            annual_kwh = 350000.0  # ~1 MWh/day, small factory
    else:
        raise ValueError(f"Unknown profile_type: {profile_type}")

    # Weekend/weekday modulation for residential
    is_weekend = times.dayofweek >= 5

    # Seasonal modulation (Indonesia: wet season Nov-Mar slightly higher AC use)
    month = times.month
    seasonal = 1.0 + 0.05 * np.sin(2 * np.pi * (month - 1) / 12)

    # Map every hour to its shape
    hourly_profile = shape[times.hour].astype(float)

    # Weekend residential stays home more (morning peak shifts, evening higher)
    if profile_type == "residential":
        weekend_modifier = np.where(is_weekend, 1.15, 1.0)
        # On weekends, shift morning peak later
        weekend_morning_boost = np.where(
            is_weekend & (times.hour.isin([8, 9, 10])), 1.3, 1.0
        )
        hourly_profile *= weekend_modifier * weekend_morning_boost

    # Normalize hourly_profile so sum = 1 (for scaling to annual)
    norm_profile = hourly_profile / hourly_profile.sum()

    # Scale to annual kWh -> each value is kWh for that hour
    load_kwh = norm_profile * annual_kwh

    # Add small random noise (±5%)
    rng = np.random.default_rng(random_seed)
    noise = 1.0 + rng.normal(0, 0.03, size=len(load_kwh))
    load_kwh = load_kwh * noise

    # Return as kW (approx since each timestep is 1 hour, kWh ≈ kW)
    return pd.Series(load_kwh.values if hasattr(load_kwh, "values") else load_kwh, index=times, name="load_kw")


def get_monthly_totals(load_series: pd.Series) -> pd.Series:
    """Return monthly aggregated load in kWh."""
    return load_series.resample("ME").sum()  # month-end
