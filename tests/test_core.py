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
    assert results['system_cost'] > 0
    assert results['annual_savings'] > 0
    assert results['payback_years'] > 0
    assert np.isfinite(results['lcoe'])
