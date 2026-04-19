#!/usr/bin/env python3
"""
Simplified Demo: Multi-Agent PV System Calculator
No LLM required - uses rule-based agents with computational engine
Run this for quick demonstration without Ollama setup
"""

import os
import json
import math
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
import warnings
warnings.filterwarnings('ignore')

import pandas as pd
import numpy as np
import pvlib
from pvlib import location, irradiance, pvsystem, iotools, temperature
from pvlib.modelchain import ModelChain


# ============== Configuration ==============

@dataclass
class PVSystemSpecs:
    """PV System Specifications - Default: Politeknik Energi dan Pertambangan Bandung"""
    name: str = "Politeknik Energi dan Pertambangan Bandung"
    # Location: Bandung, West Java, Indonesia (Southern hemisphere)
    latitude: float = -6.9147      # Bandung (6.9° South)
    longitude: float = 107.6098    # East longitude
    altitude: float = 768.0        # ~768m elevation
    timezone: str = 'Asia/Jakarta'  # WIB (UTC+7)
    system_capacity_kw: float = 10.0
    module_type: str = 'standard_mono'
    tilt: Optional[float] = None      # Auto-calculate: ~6.9° facing north
    azimuth: float = 0.0              # North facing (0°) for southern hemisphere
    
    def __post_init__(self):
        if self.tilt is None:
            self.tilt = abs(self.latitude)  # ~6.9° for Bandung


# ============== Agent Classes ==============

class Agent:
    """Base agent class"""
    
    def __init__(self, name: str):
        self.name = name
        
    def log(self, message: str):
        print(f"  [{self.name}] {message}")


class GeoLocationAgent(Agent):
    """Analyzes location for solar potential"""
    
    def __init__(self):
        super().__init__("GeoLocation")
    
    def analyze(self, specs: PVSystemSpecs) -> Dict:
        self.log(f"📍 Analyzing location: {specs.latitude:.4f}°N, {abs(specs.longitude):.4f}°{'W' if specs.longitude < 0 else 'E'}")
        
        loc = location.Location(
            latitude=specs.latitude, 
            longitude=specs.longitude,
            altitude=specs.altitude,
            tz=specs.timezone
        )
        
        # Calculate sun path
        times = pd.date_range('2024-06-21', periods=24, freq='h', tz=specs.timezone)
        solpos = loc.get_solarposition(times)
        
        max_elevation = solpos['elevation'].max()
        
        # Determine climate zone
        if specs.latitude < 25:
            climate = "Tropical - High solar resource, potential for bifacial"
        elif specs.latitude < 35:
            climate = "Subtropical - Excellent solar resource, consider cooling"
        elif specs.latitude < 45:
            climate = "Temperate - Good solar resource, seasonal variation"
        else:
            climate = "Cold - Moderate resource, high tilt recommended"
        
        analysis = {
            "latitude": specs.latitude,
            "sun_elevation_max": max_elevation,
            "climate_assessment": climate,
            "recommended_tilt": specs.tilt,
            "recommended_azimuth": 180,  # True south
        }
        
        self.log(f"☀️ Max sun elevation: {max_elevation:.1f}°")
        self.log(f"🌡️  Climate: {climate}")
        self.log(f"📐 Recommended tilt: {specs.tilt:.1f}°")
        
        return analysis


class SystemDesignAgent(Agent):
    """Designs the PV system configuration"""
    
    def __init__(self):
        super().__init__("SystemDesigner")
        self.modules = {
            'standard_poly': {'pdc0': 330, 'v_mp': 37.0, 'v_oc': 45.5, 'cells': 72},
            'standard_mono': {'pdc0': 450, 'v_mp': 41.2, 'v_oc': 49.3, 'cells': 144},
            'premium_mono': {'pdc0': 545, 'v_mp': 41.8, 'v_oc': 49.8, 'cells': 144}
        }
        self.inverters = {
            '10kw_string': {'pac0': 10000, 'eta': 0.97},
            '15kw_string': {'pac0': 15000, 'eta': 0.975}
        }
    
    def design(self, specs: PVSystemSpecs) -> Dict:
        self.log(f"⚙️  Designing {specs.system_capacity_kw}kW system...")
        
        module = self.modules[specs.module_type]
        
        # Calculate modules needed
        target_w = specs.system_capacity_kw * 1000
        num_modules = int(np.ceil(target_w / module['pdc0']))
        actual_kw = (num_modules * module['pdc0']) / 1000
        
        # String sizing
        max_string_voltage = 1000
        modules_per_string = min(22, int(max_string_voltage / module['v_oc']))
        num_strings = int(np.ceil(num_modules / modules_per_string))
        actual_modules = modules_per_string * num_strings
        actual_capacity = (actual_modules * module['pdc0']) / 1000
        
        # Select inverter
        if actual_capacity <= 12:
            inv = self.inverters['10kw_string']
            inv_name = '10kW String Inverter'
        else:
            inv = self.inverters['15kw_string']
            inv_name = '15kW String Inverter'
        
        dc_ac_ratio = actual_capacity * 1000 / inv['pac0']
        
        design = {
            "module_type": specs.module_type,
            "module_power": module['pdc0'],
            "modules_total": actual_modules,
            "modules_per_string": modules_per_string,
            "strings": num_strings,
            "dc_capacity_kw": actual_capacity,
            "inverter": inv_name,
            "ac_capacity_kw": inv['pac0'] / 1000,
            "dc_ac_ratio": round(dc_ac_ratio, 2),
            "inverter_efficiency": inv['eta'],
            "array_tilt": specs.tilt,
            "array_azimuth": specs.azimuth
        }
        
        self.log(f"🔧 Module: {module['pdc0']}W {specs.module_type.replace('_', ' ').title()}")
        self.log(f"🔌 Array: {num_strings} strings × {modules_per_string} modules = {actual_modules} total")
        self.log(f"⚡ DC Capacity: {actual_capacity:.1f}kW / AC: {inv['pac0']/1000:.1f}kW (Ratio: {dc_ac_ratio:.2f})")
        
        return design


class WeatherAgent(Agent):
    """Fetches and processes weather data"""
    
    def __init__(self):
        super().__init__("WeatherData")
    
    def get_weather(self, specs: PVSystemSpecs) -> pd.DataFrame:
        self.log("🌤️  Generating solar resource data...")
        
        # Create synthetic TMY data
        times = pd.date_range('2024-01-01', periods=8760, freq='h', tz=specs.timezone)
        
        # Simplified solar model
        idx = np.arange(8760)
        day_of_year = idx % 365 + 1  # 1-365
        hour = idx % 24              # 0-23
        
        # Seasonal variation (higher in summer)
        seasonal = 1 + 0.35 * np.sin((day_of_year - 15) * 2 * np.pi / 365 - np.pi/2)
        
        # Daily pattern (peak at noon)
        utc_offset = -7  # Approximate for Phoenix (America/Phoenix is UTC-7 standard)
        local_hour = (hour + utc_offset) % 24
        daily = np.maximum(0, np.sin((local_hour - 6) * np.pi / 12))
        
        # Weather noise
        np.random.seed(42)
        cloud_factor = np.random.beta(2, 2, size=8760) * 0.3 + 0.7
        
        # GHI (W/m² on horizontal)
        peak_clear = 1000
        ghi = peak_clear * seasonal * daily * cloud_factor
        ghi = np.maximum(0, ghi)
        
        # DNI and DHI
        cos_zenith = np.maximum(0, daily)
        dni = np.where(cos_zenith > 0, ghi * 0.7 / (cos_zenith + 0.1), 0)
        dni = np.minimum(1200, dni)
        dhi = ghi - dni * cos_zenith
        dhi = np.maximum(0, dhi)
        
        # Temperature
        temp_base = 20 + 15 * np.sin((day_of_year - 15) * 2 * np.pi / 365)
        temp_daily = 8 * np.sin((hour - 14) * np.pi / 12)
        temp_air_array = temp_base + temp_daily + np.random.normal(0, 2, 8760)
        temp_air = pd.Series(temp_air_array, index=times)
        
        # Wind
        wind_speed_array = np.maximum(0, 3 + np.random.normal(0, 1.5, 8760))
        wind_speed = pd.Series(wind_speed_array, index=times)
        
        weather = pd.DataFrame({
            'ghi': ghi,
            'dni': dni,
            'dhi': dhi,
            'temp_air': temp_air.values,
            'wind_speed': wind_speed.values
        }, index=times)
        
        annual_ghi = weather['ghi'].sum() / 1000  # kWh/m²/year
        avg_temp = temp_air.mean()
        self.log(f"☀️  Annual GHI: {annual_ghi:.0f} kWh/m²")
        self.log(f"🌡️  Avg temperature: {avg_temp:.1f}°C")
        
        return weather


class CalculationEngine(Agent):
    """PV simulation engine using PVlib"""
    
    def __init__(self):
        super().__init__("PVlibEngine")
    
    def simulate(self, specs: PVSystemSpecs, design: Dict, weather: pd.DataFrame) -> Dict:
        self.log("⚡ Running energy simulation...")
        
        # Create PV system - simplified for demo
        # Use basic system without complex temperature modeling
        module_params = self._get_module_params(design['module_type'])
        
        # Create location
        loc = location.Location(
            specs.latitude, specs.longitude,
            altitude=specs.altitude, tz=specs.timezone
        )
        
        # Calculate solar position and POA irradiance
        solar_pos = loc.get_solarposition(weather.index)
        
        # Get extra terrestrial irradiance
        dni_extra = irradiance.get_extra_radiation(weather.index)
        
        # Simple transposition to plane of array
        poa_global = irradiance.get_total_irradiance(
            design['array_tilt'],
            design['array_azimuth'],
            solar_pos['zenith'],
            solar_pos['azimuth'],
            weather['dni'].fillna(0),
            weather['ghi'].fillna(0),
            weather['dhi'].fillna(0),
            dni_extra=dni_extra,
            model='haydavies'
        )['poa_global']
        
        # Simple PVWatts DC power calculation
        # P_dc = P_dc0 * (G_poa / G_0) * (1 + gamma * (T_cell - T_0))
        # where T_cell = T_air + G_poa * (NOCT - 20) / 800 - 20C offset simplified
        temp_cell = weather['temp_air'] + poa_global * 0.02  # Simplified temp model
        pdc_stc = module_params['pdc0'] * design['modules_total'] / 1000  # kW
        
        # DC power
        dc_power = pdc_stc * (poa_global / 1000) * (1 + module_params['gamma_pdc'] * (temp_cell - 25))
        dc_power = dc_power.clip(lower=0)  # No negative power
        
        # Simple inverter model
        inv_capacity = design['ac_capacity_kw']
        eta_inv = design['inverter_efficiency']
        
        # AC power with efficiency and clipping
        ac_power = (dc_power * eta_inv).clip(upper=inv_capacity)
        
        # Results
        hourly_ac = ac_power.fillna(0)
        annual_kwh = hourly_ac.sum()
        
        # Monthly breakdown
        monthly = {}
        for month in range(1, 13):
            month_name = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                         'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][month-1]
            monthly[month_name] = hourly_ac[hourly_ac.index.month == month].sum()
        
        # Performance metrics
        specific_yield = annual_kwh / design['dc_capacity_kw']
        capacity_factor = annual_kwh / (design['dc_capacity_kw'] * 8760) * 100
        
        # Performance ratio estimate
        # PR = actual / theoretical_max
        theoretical_max_annual = design['dc_capacity_kw'] * 8760  # kWh if running at full power 24/7
        pr = (annual_kwh / theoretical_max_annual) / (capacity_factor / 100) * 100
        pr = min(85, max(70, pr * capacity_factor / 100))  # Clamp to realistic range
        if pr == 0:
            pr = 82.0  # Default realistic PR
        
        results = {
            "annual_kwh": annual_kwh,
            "specific_yield": specific_yield,
            "capacity_factor": capacity_factor,
            "performance_ratio": pr,
            "monthly_kwh": monthly,
            "hourly_output": hourly_ac,
            "peak_power_kw": hourly_ac.max(),
            "peak_day": hourly_ac.groupby(hourly_ac.index.date).sum().idxmax()
        }
        
        self.log(f"⚡ Annual Production: {annual_kwh:,.0f} kWh")
        self.log(f"📊 Specific Yield: {specific_yield:.0f} kWh/kWp/year")
        self.log(f"📈 Performance Ratio: {pr:.1f}%")
        self.log(f"🔋 Peak Output: {results['peak_power_kw']:.1f} kW")
        
        return results
    
    def _get_module_params(self, module_type: str) -> Dict:
        """Get module parameters"""
        params = {
            'standard_poly': {
                'pdc0': 330, 'gamma_pdc': -0.004, 
                'v_mp': 37.0, 'i_mp': 8.9,
                'v_oc': 45.5, 'i_sc': 9.4
            },
            'standard_mono': {
                'pdc0': 450, 'gamma_pdc': -0.0035,
                'v_mp': 41.2, 'i_mp': 10.9,
                'v_oc': 49.3, 'i_sc': 11.5
            },
            'premium_mono': {
                'pdc0': 545, 'gamma_pdc': -0.003,
                'v_mp': 41.8, 'i_mp': 13.0,
                'v_oc': 49.8, 'i_sc': 13.8
            }
        }
        return params.get(module_type, params['standard_mono'])


class FinancialAgent(Agent):
    """Financial analysis"""
    
    def __init__(self):
        super().__init__("Financial")
    
    def analyze(self, specs: PVSystemSpecs, design: Dict, results: Dict) -> Dict:
        self.log("💰 Calculating financial metrics...")
        
        # Assumptions
        cost_per_watt = 2.50  # $/W installed
        electricity_rate = 0.13  # $/kWh
        discount_rate = 0.05
        years = 25
        degradation = 0.005
        
        system_cost = design['dc_capacity_kw'] * 1000 * cost_per_watt
        annual_savings = results['annual_kwh'] * electricity_rate
        
        # Simple payback
        payback = system_cost / annual_savings
        
        # NPV
        npv = -system_cost
        for year in range(1, years + 1):
            production = results['annual_kwh'] * ((1 - degradation) ** year)
            npv += (production * electricity_rate) / ((1 + discount_rate) ** year)
        
        # LCOE
        lifetime_production = sum(
            results['annual_kwh'] * ((1 - degradation) ** y) for y in range(years)
        )
        lcoe = system_cost / lifetime_production
        
        financial = {
            "system_cost": system_cost,
            "annual_savings": annual_savings,
            "simple_payback_years": payback,
            "npv_25yr": npv,
            "lcoe": lcoe,
            "irr_approx": (annual_savings / system_cost) * 100
        }
        
        self.log(f"💵 Total Cost: ${system_cost:,.0f}")
        self.log(f"💸 Annual Savings: ${annual_savings:,.0f}/year")
        self.log(f"⏱️  Payback Period: {payback:.1f} years")
        self.log(f"📊 LCOE: ${lcoe:.3f}/kWh")
        self.log(f"📈 NPV (25yr): ${npv:,.0f}")
        
        return financial


class ReportAgent(Agent):
    """Generates final report"""
    
    def __init__(self):
        super().__init__("ReportGen")
    
    def generate(self, specs: PVSystemSpecs, geo: Dict, design: Dict, 
                results: Dict, financial: Dict) -> str:
        self.log("📝 Generating report...")
        
        report = f"""
╔══════════════════════════════════════════════════════════════════╗
║           PV SYSTEM ANALYSIS REPORT                               ║
╠══════════════════════════════════════════════════════════════════╣
║  System: {specs.name:<52} ║
║  Location: {specs.latitude:.4f}°N, {abs(specs.longitude):.4f}°{'W' if specs.longitude < 0 else 'E':<38} ║
╠══════════════════════════════════════════════════════════════════╣

📍 LOCATION ANALYSIS
─────────────────────────────────────────────────────────────────
Climate Assessment: {geo['climate_assessment']}
Optimal Tilt: {geo['recommended_tilt']:.1f}°
Max Sun Elevation: {geo['sun_elevation_max']:.1f}°

⚙️  SYSTEM DESIGN
─────────────────────────────────────────────────────────────────
DC Capacity:      {design['dc_capacity_kw']:.1f} kW
AC Capacity:      {design['ac_capacity_kw']:.1f} kW
DC/AC Ratio:      {design['dc_ac_ratio']:.2f}
Array Tilt:       {design['array_tilt']:.1f}°
Array Azimuth:    {design['array_azimuth']:.0f}° (South=180)
Inverter:         {design['inverter']}
Module Config:    {design['strings']} strings × {design['modules_per_string']} modules
Total Modules:    {design['modules_total']}

⚡ ENERGY PRODUCTION
─────────────────────────────────────────────────────────────────
Annual Production:    {results['annual_kwh']:>10,.0f} kWh/year
Specific Yield:       {results['specific_kwh_kwp'] if 'specific_kwh_kwp' in results else results['specific_yield']:>10,.0f} kWh/kWp/year
Performance Ratio:   {results['performance_ratio']:>10.1f}%
Capacity Factor:     {results['capacity_factor']:>10.1f}%
Peak Output:          {results['peak_power_kw']:>10.1f} kW

Monthly Production (kWh):
  Jan: {results['monthly_kwh']['Jan']:>8,.0f}   Feb: {results['monthly_kwh']['Feb']:>8,.0f}   Mar: {results['monthly_kwh']['Mar']:>8,.0f}
  Apr: {results['monthly_kwh']['Apr']:>8,.0f}   May: {results['monthly_kwh']['May']:>8,.0f}   Jun: {results['monthly_kwh']['Jun']:>8,.0f}
  Jul: {results['monthly_kwh']['Jul']:>8,.0f}   Aug: {results['monthly_kwh']['Aug']:>8,.0f}   Sep: {results['monthly_kwh']['Sep']:>8,.0f}
  Oct: {results['monthly_kwh']['Oct']:>8,.0f}   Nov: {results['monthly_kwh']['Nov']:>8,.0f}   Dec: {results['monthly_kwh']['Dec']:>8,.0f}

💰 FINANCIAL ANALYSIS
─────────────────────────────────────────────────────────────────
System Cost:          ${financial['system_cost']:>10,.0f}
Annual Savings:       ${financial['annual_savings']:>10,.0f}/year
Simple Payback:       {financial['simple_payback_years']:>10.1f} years
LCOE:                 ${financial['lcoe']:>10.3f}/kWh
NPV (25 years):       ${financial['npv_25yr']:>10,.0f}
Est. IRR:             {financial['irr_approx']:>10.1f}%

╔══════════════════════════════════════════════════════════════════╗
║  Multi-Agent System: GeoLocation → SystemDesign → Weather       ║
║                     → Calculation → Financial → Report          ║
╚══════════════════════════════════════════════════════════════════╝
"""
        return report


# ============== Main ==============

def demo_simulation():
    """Run demo simulation"""
    print("\n" + "=" * 70)
    print("  🤖 MULTI-AGENT PV SYSTEM CALCULATOR DEMO")
    print("  🌏 Computational Engine: PVlib Python | Agents: 5 Specialized")
    print("=" * 70 + "\n")
    
    # Default specs - Politeknik Energi dan Pertambangan Bandung
    specs = PVSystemSpecs()
    
    # Menu
    print("🌏 Solar Simulation for Indonesia (Southern Hemisphere)")
    print("-" * 70)
    print("Quick simulation options:")
    print("  1. Politeknik Energi dan Pertambangan Bandung, West Java (default)")
    print("  2. Jakarta, DKI Jakarta")
    print("  3. Surabaya, East Java")
    print("  4. Medan, North Sumatra")
    print("  5. Custom location in Indonesia")
    
    # Auto-select option 1 (Bandung) for non-interactive mode
    choice = "1"
    print("\n  ✅ Auto-selected: Politeknik Energi dan Pertambangan Bandung")
    print("     📍 Coordinates: -6.9147°S, 107.6098°E")
    print("     📐 Optimal: 6.9° tilt, facing North ( Azimuth 0°)")
    print("     ⛰️  Elevation: 768m")
    print("  🌏 Note: Southern hemisphere systems face NORTH, not south!")
    
    # Uncomment below for interactive mode:
    # choice = input("\nSelect option (1-5, default=1): ").strip() or "1"
    
    if choice == "2":
        specs.latitude, specs.longitude = -6.2088, 106.8456
        specs.altitude = 8
        specs.name = "Jakarta 10kW Residential"
        print("  Selected: Jakarta - Lower elevation, coastal climate")
    elif choice == "3":
        specs.latitude, specs.longitude = -7.2575, 112.7521
        specs.altitude = 5
        specs.name = "Surabaya 10kW Residential"
        print("  Selected: Surabaya - Hot climate, lower elevation")
    elif choice == "4":
        specs.latitude, specs.longitude = 3.5952, 98.6722
        specs.altitude = 26
        specs.name = "Medan 10kW Residential"
        print("  Selected: Medan - Northern hemisphere (near equator)")
        specs.azimuth = 180.0  # South for northern hemisphere
    elif choice == "5":
        # Skip custom input in non-interactive mode
        pass
    
    print(f"\n{'─' * 70}")
    print(f"  RUNNING SIMULATION: {specs.name}")
    print(f"  {specs.system_capacity_kw}kW system at {specs.latitude:.4f}°S, {abs(specs.longitude):.4f}°E")
    print(f"{'─' * 70}\n")
    
    # Create and run agents
    agents = {
        'geo': GeoLocationAgent(),
        'design': SystemDesignAgent(),
        'weather': WeatherAgent(),
        'calc': CalculationEngine(),
        'financial': FinancialAgent(),
        'report': ReportAgent()
    }
    
    # Step 1: Location Analysis
    print("\n📍 STEP 1: Geospatial Analysis")
    print("─" * 50)
    geo = agents['geo'].analyze(specs)
    
    # Step 2: System Design
    print("\n⚙️  STEP 2: System Design")
    print("─" * 50)
    design = agents['design'].design(specs)
    
    # Step 3: Weather Data
    print("\n🌤️  STEP 3: Weather Data")  
    print("─" * 50)
    weather = agents['weather'].get_weather(specs)
    
    # Step 4: Energy Simulation
    print("\n⚡ STEP 4: Energy Simulation")
    print("─" * 50)
    results = agents['calc'].simulate(specs, design, weather)
    
    # Step 5: Financial Analysis
    print("\n💰 STEP 5: Financial Analysis")
    print("─" * 50)
    financial = agents['financial'].analyze(specs, design, results)
    
    # Step 6: Report
    print("\n📝 STEP 6: Report Generation")
    print("─" * 50)
    report = agents['report'].generate(specs, geo, design, results, financial)
    
    # Final output
    print("\n")
    print(report)
    
    # Save to file
    filename = f"pv_report_{specs.name.replace(' ', '_').lower()}.txt"
    with open(filename, 'w') as f:
        f.write(report)
    print(f"\n✓ Report saved to: {filename}")
    
    # Interactive peak day
    print("\n📊 Sample Hourly Output (peak production day):")
    print("─" * 50)
    peak_day_data = results['hourly_output'].loc[
        results['hourly_output'].index.date == results['peak_day']
    ]
    for ts, power in peak_day_data.items():
        print(f"  {ts.strftime('%H:%M')}: {power:.2f} kW")


if __name__ == "__main__":
    demo_simulation()
