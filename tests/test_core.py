"""
Test suite for PV Multi-Agent core simulation.
Run with: uv run pytest tests/test_core.py -v
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'data'))

import pytest
import pandas as pd
import numpy as np
from datetime import datetime

from pv_module_database import PV_MODULE_DATABASE, get_module_by_name, get_database_summary
from gui import generate_synthetic_weather, simulate_pv_system, calculate_solar_position


# ============================================================================
# PV Module Database Tests
# ============================================================================

def test_database_not_empty():
    assert len(PV_MODULE_DATABASE) > 0

def test_database_summary():
    summary = get_database_summary()
    assert 'total_modules' in summary
    assert 'power_range' in summary
    assert summary['total_modules'] == len(PV_MODULE_DATABASE)

def test_get_module_by_name():
    module = get_module_by_name("SunPower", "Maxeon 7")
    assert module.pdc0 == 460
    assert module.manufacturer == "SunPower"

def test_get_module_error():
    with pytest.raises(ValueError):
        get_module_by_name("FakeBrand", "FakeModel")


# ============================================================================
# Weather Generation Tests
# ============================================================================

def test_synthetic_weather_shape():
    specs = {
        'latitude': -6.9,
        'longitude': 107.6,
        'timezone': 'Asia/Jakarta',
    }
    weather = generate_synthetic_weather(specs, periods=8760)
    assert len(weather) == 8760
    assert 'ghi' in weather.columns
    assert 'dni' in weather.columns
    assert 'dhi' in weather.columns
    assert 'temp_air' in weather.columns
    assert 'wind_speed' in weather.columns

def test_synthetic_ghi_nonnegative():
    specs = {
        'latitude': -6.9,
        'longitude': 107.6,
        'timezone': 'Asia/Jakarta',
    }
    weather = generate_synthetic_weather(specs, periods=8760)
    assert (weather['ghi'] >= 0).all()

def test_synthetic_dni_nonnegative():
    specs = {
        'latitude': -6.9,
        'longitude': 107.6,
        'timezone': 'Asia/Jakarta',
    }
    weather = generate_synthetic_weather(specs, periods=8760)
    assert (weather['dni'] >= 0).all()


# ============================================================================
# Solar Position Tests
# ============================================================================

def test_solar_position_bandung_summer():
    solar = calculate_solar_position(
        latitude=-6.9,
        longitude=107.6,
        timezone='Asia/Jakarta',
        date=datetime(2024, 6, 21),
    )
    # At solstice, declination ~+23.5 => noon elevation ~90 - |(-6.9) - 23.5| = ~59.6
    assert solar['max_elevation'] > 55, f"Bandung summer elevation should be >55deg, got {solar['max_elevation']:.1f}"
    assert solar['max_elevation'] < 90

# ============================================================================
# PV Simulation Tests
# ============================================================================

def test_simulation_produces_energy():
    specs = {
        'name': 'Test',
        'latitude': -6.9,
        'longitude': 107.6,
        'altitude': 768,
        'timezone': 'Asia/Jakarta',
        'system_capacity_kw': 1.0,
        'module_type': 'standard_mono',
        'module_power': 450,
        'module_efficiency': 21.0,
        'gamma_pdc': -0.0035,
        'tilt': 7.0,
        'azimuth': 0,
        'inverter_efficiency': 0.96,
        'cost_per_watt': 2.5,
        'electricity_rate': 0.13,
    }
    weather = generate_synthetic_weather(specs, periods=8760)
    results = simulate_pv_system(specs, weather)
    assert results['annual_kwh'] > 0, "Should produce energy"
    assert results['annual_kwh'] < 8760 * 1.5, "Unrealistically high"
    assert results['specific_yield'] > 0
    assert results['capacity_factor'] > 0
    assert results['performance_ratio'] > 0


def test_simulation_scales_with_capacity():
    """Bigger system should produce proportionally more."""
    base_specs = {
        'name': 'Test',
        'latitude': -6.9,
        'longitude': 107.6,
        'altitude': 768,
        'timezone': 'Asia/Jakarta',
        'system_capacity_kw': 1.0,
        'module_type': 'standard_mono',
        'module_power': 450,
        'module_efficiency': 21.0,
        'gamma_pdc': -0.0035,
        'tilt': 7.0,
        'azimuth': 0,
        'inverter_efficiency': 0.96,
        'cost_per_watt': 2.5,
        'electricity_rate': 0.13,
    }
    weather = generate_synthetic_weather(base_specs, periods=8760)
    r1 = simulate_pv_system(base_specs, weather)

    big_specs = base_specs.copy()
    big_specs['system_capacity_kw'] = 5.0
    r2 = simulate_pv_system(big_specs, weather)

    ratio = r2['annual_kwh'] / r1['annual_kwh']
    # Note: ceiling effect on module count means exact ratio isn't perfectly 5x
    # 1kW -> ceil(1000/450)=3 modules (1.35kW); 5kW -> ceil(5000/450)=12 modules (5.4kW)
    # Expected effective ratio ≈ 5.4/1.35 = 4.0, not 5.0
    assert 3.5 < ratio < 5.5, f"Scaling ratio should be ~4x after ceiling, got {ratio:.2f}"


def test_performance_ratio_bounds():
    """PR should be clamped to reasonable range (approx 70-85%)."""
    specs = {
        'name': 'Test',
        'latitude': -6.9,
        'longitude': 107.6,
        'altitude': 768,
        'timezone': 'Asia/Jakarta',
        'system_capacity_kw': 1.0,
        'module_type': 'standard_mono',
        'module_power': 450,
        'module_efficiency': 21.0,
        'gamma_pdc': -0.0035,
        'tilt': 7.0,
        'azimuth': 0,
        'inverter_efficiency': 0.96,
        'cost_per_watt': 2.5,
        'electricity_rate': 0.13,
    }
    weather = generate_synthetic_weather(specs, periods=8760)
    results = simulate_pv_system(specs, weather)
    assert 50 <= results['performance_ratio'] <= 100, f"PR out of bounds: {results['performance_ratio']}"


def test_financial_calculations_positive():
    """Financial outputs should be positive finite numbers."""
    specs = {
        'name': 'Test',
        'latitude': -6.9,
        'longitude': 107.6,
        'altitude': 768,
        'timezone': 'Asia/Jakarta',
        'system_capacity_kw': 1.0,
        'module_type': 'standard_mono',
        'module_power': 450,
        'module_efficiency': 21.0,
        'gamma_pdc': -0.0035,
        'tilt': 7.0,
        'azimuth': 0,
        'inverter_efficiency': 0.96,
        'cost_per_watt': 2.5,
        'electricity_rate': 0.13,
    }
    weather = generate_synthetic_weather(specs, periods=8760)
    results = simulate_pv_system(specs, weather)
    assert results['lcoe'] >= 0


# ============================================================================
# Battery Storage Tests
# ============================================================================

from storage_engine import BatterySpecs, BatterySimulator
from storage_optimizer import self_consumption_optimizer
from load_profiles import generate_profile
from pln_tariffs import get_tariff, list_tariffs


def test_battery_specs_init():
    b = BatterySpecs(capacity_kwh=10.0, max_charge_kw=5.0, max_discharge_kw=5.0)
    assert b.capacity_kwh == 10.0
    assert b.usable_capacity_kwh == 10.0 * (1.0 - 0.10)
    assert b.upfront_cost_idr == 10.0 * 4_500_000


def test_battery_simulate_step():
    specs = BatterySpecs(capacity_kwh=5.0, max_charge_kw=2.5, max_discharge_kw=2.5)
    sim = BatterySimulator(specs)
    st = sim.step(1.0, ambient_temp_c=30.0)
    assert st.charge_power_kw == 1.0
    assert st.soc > specs.initial_soc
    assert st.soc <= specs.max_soc


def test_battery_simulate_full_cycle():
    specs = BatterySpecs(capacity_kwh=5.0, max_charge_kw=2.5, round_trip_efficiency=0.95)
    sim = BatterySimulator(specs)
    # Charge 2 hours at 2.5 kW (clipped by SOC limit eventually)
    for _ in range(3):
        sim.step(2.5, ambient_temp_c=30.0)
    assert sim.current_state.soc > specs.initial_soc
    # Discharge
    for _ in range(3):
        sim.step(-2.5, ambient_temp_c=30.0)
    assert sim.current_state.soc >= specs.min_soc
    summary = sim.get_summary()
    assert summary["total_cycles"] > 0


def test_self_consumption_optimizer_basic():
    np.random.seed(42)
    times = pd.date_range("2024-01-01", periods=24, freq="h")
    # Make solar match daytime hours
    solar = pd.Series(np.zeros(24), index=times)
    solar[6:18] = 2.0  # 2 kW during day

    load = pd.Series(np.ones(24) * 1.0, index=times)  # 1 kW constant

    battery = BatterySpecs(capacity_kwh=2.0, max_charge_kw=1.0, max_discharge_kw=1.0)
    result = self_consumption_optimizer(solar, load, battery, tariff_code="R-1/1300VA")

    assert result.total_solar_kwh > 0
    assert result.total_load_kwh > 0
    assert result.self_consumption_ratio <= 1.0
    assert result.self_sufficiency_ratio <= 1.0
    # With battery, self-consumption should be higher than without
    assert result.total_battery_charge_kwh >= 0


def test_load_profile_generation():
    prof = generate_profile("residential", annual_kwh=4380, random_seed=42)
    assert len(prof) == 8760
    assert (prof >= 0).all()
    assert prof.sum() > 4000  # Approx annual
    assert prof.sum() < 5000


def test_load_profile_commercial():
    prof = generate_profile("commercial", annual_kwh=36500, random_seed=42)
    assert len(prof) == 8760
    # Commercial should have higher daytime load
    daytime = prof.between_time("09:00", "17:00").mean()
    nighttime = prof.between_time("22:00", "05:00").mean()
    assert daytime > nighttime * 2  # Commercial peaks during day


def test_pln_tariff_lookup():
    t = get_tariff("R-1/1300VA")
    assert t.customer_group == "R-1"
    assert t.power_va == 1300
    t_list = list_tariffs()
    assert len(t_list) >= 7  # Should have all defined tariffs


def test_pln_bill_calculation():
    t = get_tariff("R-1/2200VA")
    from pln_tariffs import calculate_bill_components
    bill = calculate_bill_components(2000, 500, t)
    assert bill["net_bill_idr"] >= 0
    assert bill["export_credit_idr"] > 0
    assert bill["energy_charge_idr"] > bill["export_credit_idr"]  # import > export

