"""
Multi-Agent PV System Calculator
Based on PVlib Python - Open-source PV system modeling
"""

import os
import json
import math
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field

import pandas as pd
import numpy as np
import pvlib
from pvlib import location, irradiance, pvsystem, iotools, temperature
from pvlib.modelchain import ModelChain
import ollama


# ============== Data Structures ==============

@dataclass
class PVSystemSpecs:
    """PV System Specifications - Default: Politeknik Energi dan Pertambangan Bandung"""
    # Location: Politeknik Energi dan Pertambangan Bandung, West Java, Indonesia
    # Coordinates approximated for Bandung area
    latitude: float = -6.9147      # Bandung, West Java (Southern hemisphere)
    longitude: float = 107.6098    # East longitude
    altitude: float = 768.0        # Bandung elevation ~768m
    timezone: str = 'Asia/Jakarta'  # Western Indonesia Time (WIB)
    system_capacity_kw: float = 10.0
    module_type: str = 'standard'
    module_power: float = 450.0  # Watts
    tilt: Optional[float] = None  # Auto-calculate if None
    azimuth: float = 0.0  # North facing (for Southern hemisphere)
    inverter_efficiency: float = 0.96
    dc_ac_ratio: float = 1.2
    
    def __post_init__(self):
        if self.tilt is None:
            # Optimal tilt ~ latitude (absolute value), facing north in southern hemisphere
            self.tilt = abs(self.latitude)


@dataclass 
class WeatherData:
    """Solar resource data"""
    ghi: pd.Series = field(default_factory=pd.Series)
    dni: pd.Series = field(default_factory=pd.Series)
    dhi: pd.Series = field(default_factory=pd.Series)
    temp_air: pd.Series = field(default_factory=pd.Series)
    wind_speed: pd.Series = field(default_factory=pd.Series)
    times: pd.DatetimeIndex = field(default_factory=lambda: pd.DatetimeIndex([]))


@dataclass
class SimulationResult:
    """Annual simulation results"""
    annual_energy_kwh: float = 0.0
    specific_yield_kwh_kwp: float = 0.0
    performance_ratio: float = 0.0
    capacity_factor: float = 0.0
    hourly_output: pd.Series = field(default_factory=pd.Series)
    monthly_energy: Dict[str, float] = field(default_factory=dict)
    losses: Dict[str, float] = field(default_factory=dict)


# ============== Agent Base Class ==============

class PVAgent:
    """Base class for PV system agents"""
    
    def __init__(self, name: str, model: str = "gemma4:e4b"):
        self.name = name
        self.model = model
        self.memory = []
        
    def think(self, task: str, context: Dict = None) -> str:
        """Use LLM for reasoning and planning"""
        context_str = json.dumps(context, indent=2, default=str) if context else "No context"
        
        prompt = f"""You are {self.name}, an expert in photovoltaic system engineering.

TASK: {task}

CONTEXT:
{context_str}

RESPOND AS {self.name}:
Provide your analysis, reasoning, and specific recommendations. Be concise but thorough.
"""
        
        try:
            response = ollama.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a PV system engineering AI agent."},
                    {"role": "user", "content": prompt}
                ],
                options={"temperature": 0.3}
            )
            return response['message']['content']
        except Exception as e:
            return f"[LLM Error: {e}] - Proceeding with default values."
    
    def log(self, message: str):
        """Log agent activity"""
        print(f"[{self.name}] {message}")


# ============== Specialized Agents ==============

class GeolocationAgent(PVAgent):
    """Agent for geospatial calculations and solar geometry"""
    
    def __init__(self, model: str = "llama3.2"):
        super().__init__("GeolocationAgent", model)
    
    def analyze_location(self, specs: PVSystemSpecs) -> Dict:
        """Calculate solar geometry and optimal parameters"""
        self.log(f"Analyzing location: {specs.latitude:.4f}°, {specs.longitude:.4f}°")
        
        # Calculate key solar parameters
        loc = location.Location(
            latitude=specs.latitude, 
            longitude=specs.longitude,
            altitude=specs.altitude,
            tz=specs.timezone
        )
        
        # Get solar position for entire year (hourly)
        times = pd.date_range(
            start='2024-01-01', 
            end='2024-12-31 23:00', 
            freq='h',
            tz=specs.timezone
        )
        
        solar_pos = loc.get_solarposition(times)
        
        # Calculate optimal tilt for each month
        months = range(1, 13)
        optimal_tilts = []
        
        for month in months:
            # Average solar elevation at solar noon for this month
            month_days = solar_pos[solar_pos.index.month == month]
            noon_elevations = month_days.groupby(month_days.index.day)['elevation'].max()
            avg_elevation = noon_elevations.mean()
            # Optimal tilt is roughly 90 - elevation
            optimal_tilt = max(0, 90 - avg_elevation)
            optimal_tilts.append(optimal_tilt)
        
        analysis = {
            "location_info": {
                "latitude": specs.latitude,
                "longitude": specs.longitude,
                "altitude_m": specs.altitude,
                "timezone": specs.timezone
            },
            "annual_sun_path": {
                "max_solar_elevation": float(solar_pos['elevation'].max()),
                "min_solar_elevation": float(solar_pos['elevation'].min()),
            },
            "optimal_tilt_by_month": {f"month_{i+1}": round(t, 1) for i, t in enumerate(optimal_tilts)},
            "recommended_fixed_tilt": round(np.mean(optimal_tilts), 1),
            "suggested_azimuth": 180 if abs(specs.latitude) < 23.5 else (180 if specs.latitude > 0 else 0)
        }
        
        # Get LLM reasoning
        llm_insight = self.think(
            "Recommend optimal tilt and azimuth for this location, considering seasonal sun angles and practical constraints.",
            analysis
        )
        analysis['llm_insight'] = llm_insight
        
        return analysis
    
    def calculate_solar_angles(self, lat: float, lon: float, timestamp: datetime) -> Dict:
        """Calculate solar position for a specific time"""
        loc = location.Location(lat, lon)
        solar_pos = loc.get_solarposition(timestamp)
        return {
            'elevation': float(solar_pos['elevation']),
            'azimuth': float(solar_pos['azimuth']),
            'zenith': float(solar_pos['zenith'])
        }


class WeatherAgent(PVAgent):
    """Agent for fetching and processing meteorological data"""
    
    def __init__(self, model: str = "llama3.2"):
        super().__init__("WeatherAgent", model)
        self.has_openmeteo = True
        
    def fetch_weather_data(self, specs: PVSystemSpecs) -> WeatherData:
        """Fetch typical meteorological year data from Open-Meteo API"""
        self.log(f"Fetching weather data for coordinates: {specs.latitude}, {specs.longitude}")
        
        weather = WeatherData()
        
        try:
            import openmeteo_requests
            import niquests
            
            # Open-Meteo API for solar radiation
            url = "https://archive-api.open-meteo.io/v1/archive"
            params = {
                "latitude": specs.latitude,
                "longitude": specs.longitude,
                "start_date": "2023-01-01",
                "end_date": "2023-12-31",
                "hourly": [
                    "shortwave_radiation",
                    "direct_normal_irradiance", 
                    "diffuse_radiation",
                    "temperature_2m",
                    "windspeed_10m"
                ],
                "timezone": "auto"
            }
            
            session = niquests.Session()
            response = session.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            hourly = data['hourly']
            
            # Create DataFrame
            times = pd.to_datetime(hourly['time'])
            weather.times = times
            weather.ghi = pd.Series(hourly['shortwave_radiation'], index=times)
            weather.dni = pd.Series(hourly['direct_normal_irradiance'], index=times)
            weather.dhi = pd.Series(hourly['diffuse_radiation'], index=times)
            weather.temp_air = pd.Series(hourly['temperature_2m'], index=times)
            weather.wind_speed = pd.Series(hourly['windspeed_10m'], index=times)
            
            self.log(f"Successfully fetched {len(times)} hours of weather data")
            
        except Exception as e:
            self.log(f"Using synthetic data instead: {e}")
            weather = self._generate_synthetic_data(specs)
        
        return weather
    
    def _generate_synthetic_data(self, specs: PVSystemSpecs) -> WeatherData:
        """Generate representative synthetic weather data using PVLib TMY functionality"""
        self.log("Generating representative TMY data...")
        
        # Use PVLib's built-in data or create representative data
        try:
            # Try to get data for Tucson, AZ (similar to Phoenix)
            from io import StringIO
            
            # Create hourly data for a year
            times = pd.date_range('2024-01-01', periods=8760, freq='h', tz=specs.timezone)
            
            weather = WeatherData()
            weather.times = times
            
            # Simple sinusoidal model for GHI (Daily + Annual cycles)
            day_of_year = times.dayofyear
            hour = times.hour
            
            # Annual variation (higher in summer)
            annual_factor = 1 + 0.3 * np.sin((day_of_year - 15) * 2 * np.pi / 365 - np.pi/2)
            
            # Daily variation (peak at noon)
            solar_time = hour + (specs.longitude % 15) / 15
            daily_factor = np.maximum(0, np.sin((solar_time - 6) * np.pi / 12))
            
            # Peak GHI ~1000 W/m² in summer
            peak_ghi = 1000
            weather.ghi = pd.Series(peak_ghi * annual_factor * daily_factor, index=times)
            
            # DNI is approximately GHI / cos(zenith) during clear sky
            weather.dni = weather.ghi * 0.8
            weather.dhi = weather.ghi * 0.3
            
            # Temperature
            weather.temp_air = pd.Series(
                20 + 15 * np.sin((day_of_year - 15) * 2 * np.pi / 365) + 
                5 * np.sin((hour - 14) * np.pi / 12),
                index=times
            )
            
            weather.wind_speed = pd.Series(3.0, index=times)
            
            return weather
            
        except Exception as e:
            self.log(f"Error in synthetic data: {e}")
            return WeatherData()
    
    def calculate_plane_of_array_irradiance(self, weather: WeatherData, specs: PVSystemSpecs) -> pd.Series:
        """Calculate POA irradiance"""
        # Get solar position
        loc = location.Location(
            specs.latitude, specs.longitude, 
            altitude=specs.altitude, tz=specs.timezone
        )
        solar_pos = loc.get_solarposition(weather.times)
        
        # Transposition model (Hay-Davies)
        poa = irradiance.get_total_irradiance(
            specs.tilt,
            specs.azimuth,
            solar_pos['zenith'],
            solar_pos['azimuth'],
            weather.dni.fillna(0),
            weather.ghi.fillna(0),
            weather.dhi.fillna(0),
            dni_extra=None,
            model='haydavies'
        )
        
        return poa['poa_global']


class SystemDesignAgent(PVAgent):
    """Agent for PV system design and component sizing"""
    
    def __init__(self, model: str = "llama3.2"):
        super().__init__("SystemDesignAgent", model)
        self.module_db = self._load_module_database()
        self.inverter_db = self._load_inverter_database()
    
    def _load_module_database(self) -> Dict:
        """Load available PV module data"""
        # Common commercial modules
        return {
            'standard_poly': {
                'pdc0': 330, 'gamma_pdc': -0.004, 'v_mp': 37.0, 
                'i_mp': 8.9, 'v_oc': 45.5, 'i_sc': 9.4,
                'cells_in_series': 72
            },
            'standard_mono': {
                'pdc0': 450, 'gamma_pdc': -0.0035, 'v_mp': 41.2,
                'i_mp': 10.9, 'v_oc': 49.3, 'i_sc': 11.5,
                'cells_in_series': 144
            },
            'premium_mono': {
                'pdc0': 545, 'gamma_pdc': -0.003, 'v_mp': 41.8,
                'i_mp': 13.0, 'v_oc': 49.8, 'i_sc': 13.8,
                'cells_in_series': 144
            }
        }
    
    def _load_inverter_database(self) -> Dict:
        """Load available inverter data"""
        return {
            'string_10kw': {'pac0': 10000, 'pdc0': 11000, 'eta_inv_nom': 0.97},
            'string_15kw': {'pac0': 15000, 'pdc0': 16500, 'eta_inv_nom': 0.975},
            'hybrid_10kw': {'pac0': 10000, 'pdc0': 13000, 'eta_inv_nom': 0.98}
        }
    
    def design_system(self, specs: PVSystemSpecs) -> Dict:
        """Design PV system configuration"""
        self.log(f"Designing {specs.system_capacity_kw}kW system")
        
        # Select module
        if specs.module_type == 'premium':
            module_name = 'premium_mono'
        elif specs.module_type == 'standard':
            module_name = 'standard_mono'
        else:
            module_name = 'standard_poly'
        
        module = self.module_db[module_name]
        
        # Calculate number of modules
        num_modules = int(np.ceil(specs.system_capacity_kw * 1000 / module['pdc0']))
        actual_capacity = num_modules * module['pdc0'] / 1000  # kW
        
        # String sizing (voltage limits)
        # Typical string inverter max input: 1000V DC
        modules_per_string = min(24, int(1000 / module['v_oc']))
        num_strings = int(np.ceil(num_modules / modules_per_string))
        
        # Adjust to match
        actual_modules = modules_per_string * num_strings
        actual_capacity = actual_modules * module['pdc0'] / 1000
        
        # Select inverter
        if actual_capacity <= 12:
            inverter_name = 'string_10kw'
        elif actual_capacity <= 17:
            inverter_name = 'string_15kw'
        else:
            inverter_name = 'string_15kw'
        
        inverter = self.inverter_db[inverter_name]
        
        # Calculate DC/AC ratio
        dc_ac_ratio = (actual_capacity * 1000) / inverter['pac0']
        
        design = {
            "system_summary": {
                "target_capacity_kw": specs.system_capacity_kw,
                "actual_capacity_kw": round(actual_capacity, 2),
                "dc_ac_ratio": round(dc_ac_ratio, 2),
                "num_modules": actual_modules,
                "modules_per_string": modules_per_string,
                "num_strings": num_strings
            },
            "module_specifications": module,
            "module_model": module_name,
            "inverter_specifications": inverter,
            "inverter_model": inverter_name,
            "array_configuration": {
                "tilt_degrees": specs.tilt,
                "azimuth_degrees": specs.azimuth,
                "ground_coverage_ratio": 0.4
            }
        }
        
        # LLM review
        llm_review = self.think(
            "Review this PV system design and suggest optimizations. Consider shading, mismatch losses, voltage drop, and clipping losses.",
            design
        )
        design['llm_review'] = llm_review
        
        return design


class CalculationEngine:
    """Physics-based calculation engine (no LLM - precise math)"""
    
    def __init__(self):
        self.name = "CalculationEngine"
    
    def simulate_annual_production(self, 
                                   specs: PVSystemSpecs, 
                                   weather: WeatherData,
                                   design: Dict) -> SimulationResult:
        """Run annual energy simulation using PVlib"""
        print(f"[{self.name}] Running annual simulation...")
        
        # Create location
        loc = location.Location(
            specs.latitude, specs.longitude,
            altitude=specs.altitude, tz=specs.timezone
        )
        
        # Use the same simplified approach as demo.py (proven to work)
        # Get module parameters
        module_params = design['module_specifications']
        
        # Create location
        loc = location.Location(
            specs.latitude, specs.longitude,
            altitude=specs.altitude, tz=specs.timezone
        )
        
        # Calculate solar position and POA irradiance
        from pvlib import irradiance
        solar_pos = loc.get_solarposition(weather.times)
        dni_extra = irradiance.get_extra_radiation(weather.times)
        
        poa_global = irradiance.get_total_irradiance(
            specs.tilt,
            specs.azimuth,
            solar_pos['zenith'],
            solar_pos['azimuth'],
            weather.dni.fillna(0),
            weather.ghi.fillna(0),
            weather.dhi.fillna(0),
            dni_extra=dni_extra,
            model='haydavies'
        )['poa_global']
        
        # Simple PVWatts DC power
        temp_cell = weather.temp_air + poa_global * 0.02
        actual_capacity = design['system_summary']['actual_capacity_kw']
        
        # DC power (account for temperature)
        gamma = module_params.get('gamma_pdc', -0.003)
        dc_power = actual_capacity * (poa_global / 1000) * (1 + gamma * (temp_cell - 25))
        dc_power = dc_power.clip(lower=0)
        
        # Simple inverter
        ac_power = (dc_power * specs.inverter_efficiency).clip(
            upper=design['inverter_specifications']['pac0'] / 1000
        )
        
        # Results
        hourly_ac = ac_power.fillna(0)
        annual_kwh = hourly_ac.sum()
        
        # Monthly breakdown
        monthly = {}
        for month_idx, month_name in enumerate(['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                                                 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'], 1):
            monthly[month_name] = hourly_ac[hourly_ac.index.month == month_idx].sum()
        
        # Performance metrics
        specific_yield = annual_kwh / actual_capacity
        capacity_factor = annual_kwh / (actual_capacity * 8760) * 100
        pr = min(85, max(70, specific_yield / 12))  # Estimate
        
        result = SimulationResult()
        result.hourly_output = hourly_ac
        result.annual_energy_kwh = annual_kwh
        result.specific_yield_kwh_kwp = specific_yield
        result.capacity_factor = capacity_factor
        result.performance_ratio = pr
        result.monthly_energy = monthly
        
        # Loss breakdown
        result.losses = {
            "temperature": 8.0,  # Approximate
            "soiling": 2.0,
            "mismatch": 2.0,
            "wiring": 1.5,
            "inverter": (1 - design['inverter_specifications']['eta_inv_nom']) * 100,
            "availability": 1.0,
            "degradation": 0.5
        }
        
        return result


class FinancialAgent(PVAgent):
    """Agent for financial analysis"""
    
    def __init__(self, model: str = "llama3.2"):
        super().__init__("FinancialAgent", model)
    
    def analyze(self, specs: PVSystemSpecs, result: SimulationResult, design: Dict) -> Dict:
        """Calculate financial metrics"""
        self.log("Calculating financial metrics...")
        
        # Default financial assumptions (US-centric)
        electricity_rate = 0.13  # $/kWh
        system_cost_per_watt = 2.50  # $/W installed
        
        # Try to get location-specific rates
        if abs(specs.latitude - 33.4484) < 1 and abs(specs.longitude - (-112.0740)) < 1:
            electricity_rate = 0.12  # Arizona rate
            system_cost_per_watt = 2.20
        
        system_capacity_w = design['system_summary']['actual_capacity_kw'] * 1000
        total_cost = system_capacity_w * system_cost_per_watt
        
        annual_savings = result.annual_energy_kwh * electricity_rate
        
        # Simple payback (no incentives, no discounting)
        simple_payback = total_cost / annual_savings
        
        # NPV calculation (25 years, 5% discount)
        years = 25
        discount_rate = 0.05
        degradation = 0.005  # 0.5% per year
        
        npv = -total_cost
        for year in range(1, years + 1):
            annual_production = result.annual_energy_kwh * ((1 - degradation) ** year)
            annual_benefit = annual_production * electricity_rate
            npv += annual_benefit / ((1 + discount_rate) ** year)
        
        # LCOE calculation
        total_lifetime_production = sum(
            result.annual_energy_kwh * ((1 - degradation) ** y) 
            for y in range(years)
        )
        lcoe = total_cost / total_lifetime_production
        
        financial = {
            "economic_assumptions": {
                "electricity_rate_per_kwh": electricity_rate,
                "system_cost_per_watt": system_cost_per_watt,
                "discount_rate": discount_rate,
                "analysis_period_years": years,
                "annual_degradation": degradation * 100
            },
            "financial_metrics": {
                "total_system_cost_usd": round(total_cost, 2),
                "annual_energy_production_kwh": round(result.annual_energy_kwh, 2),
                "annual_savings_usd": round(annual_savings, 2),
                "simple_payback_years": round(simple_payback, 1),
                "net_present_value_usd": round(npv, 2),
                "lcoe_per_kwh": round(lcoe, 3),
                "total_lifetime_production_mwh": round(total_lifetime_production / 1000, 1),
                "irr_estimate_percent": round((annual_savings / total_cost) * 100, 1)
            }
        }
        
        # LLM insights
        llm_insight = self.think(
            "Analyze these financial results and provide investment recommendations. Consider payback period, NPV, and typical investor expectations.",
            financial
        )
        financial['llm_insight'] = llm_insight
        
        return financial


class ReportAgent(PVAgent):
    """Agent for generating final reports"""
    
    def __init__(self, model: str = "llama3.2"):
        super().__init__("ReportAgent", model)
    
    def generate_report(self, 
                       specs: PVSystemSpecs,
                       geo_analysis: Dict,
                       design: Dict,
                       result: SimulationResult,
                       financial: Dict) -> str:
        """Generate comprehensive report"""
        self.log("Generating final report...")
        
        report_context = {
            "system_location": geo_analysis['location_info'],
            "system_design": design['system_summary'],
            "energy_production": {
                "annual_kwh": round(result.annual_energy_kwh, 2),
                "specific_yield": round(result.specific_yield_kwh_kwp, 2),
                "performance_ratio": round(result.performance_ratio, 2),
                "capacity_factor": round(result.capacity_factor, 2)
            },
            "financial_summary": financial['financial_metrics'],
            "monthly_production": result.monthly_energy
        }
        
        # Get LLM to write natural language summary
        report = self.think(
            "Write a professional PV system analysis report. Include: executive summary, system description, energy production results, financial analysis, and recommendations.",
            report_context
        )
        
        return report
    
    def generate_markdown_report(self,
                                  specs: PVSystemSpecs,
                                  geo_analysis: Dict,
                                  design: Dict,
                                  result: SimulationResult,
                                  financial: Dict) -> str:
        """Generate a formatted markdown report"""
        
        report = f"""# PV System Analysis Report

## Executive Summary

**System Location:** {specs.latitude:.4f}°N, {specs.longitude:.4f}°W  
**System Capacity:** {design['system_summary']['actual_capacity_kw']:.2f} kW DC  
**Annual Energy Production:** {result.annual_energy_kwh:,.0f} kWh  
**Specific Yield:** {result.specific_yield_kwh_kwp:.0f} kWh/kWp/year  

---

## 1. Location & Solar Resource Analysis

**Agent:** GeolocationAgent  
**Coordinates:** {specs.latitude:.4f}, {specs.longitude:.4f}  
**Elevation:** {specs.altitude}m  
**Time Zone:** {specs.timezone}

### Solar Geometry
- Maximum solar elevation: {geo_analysis['annual_sun_path']['max_solar_elevation']:.1f}°
- Minimum solar elevation: {geo_analysis['annual_sun_path']['min_solar_elevation']:.1f}°
- Recommended fixed tilt: {geo_analysis['recommended_fixed_tilt']:.1f}°

**Agent Insight:** {geo_analysis.get('llm_insight', 'N/A').split(chr(10))[0]}

---

## 2. System Design

**Agent:** SystemDesignAgent

### Module Specifications
- **Model:** {design['module_model']}
- **Rated Power:** {design['module_specifications']['pdc0']} W
- **Temperature Coefficient:** {design['module_specifications']['gamma_pdc']} /°C
- **Voc:** {design['module_specifications']['v_oc']} V
- **Isc:** {design['module_specifications']['i_sc']} A

### Array Configuration
- **Total Modules:** {design['system_summary']['num_modules']}
- **Modules per String:** {design['system_summary']['modules_per_string']}
- **Number of Strings:** {design['system_summary']['num_strings']}
- **Tilt Angle:** {design['array_configuration']['tilt_degrees']:.1f}°
- **Azimuth Angle:** {design['array_configuration']['azimuth_degrees']:.1f}° (South=180°)

### Inverter Specifications
- **Model:** {design['inverter_model']}
- **AC Power Rating:** {design['inverter_specifications']['pac0']/1000:.1f} kW
- **Efficiency:** {design['inverter_specifications']['eta_inv_nom']*100:.1f}%

**DC/AC Ratio:** {design['system_summary']['dc_ac_ratio']:.2f}

**Agent Review:** {design.get('llm_review', 'N/A').split(chr(10))[0]}

---

## 3. Energy Production Simulation

**Agent:** CalculationEngine (PVlib Python)

### Annual Results
| Metric | Value |
|--------|-------|
| Annual Production | **{result.annual_energy_kwh:,.0f} kWh** |
| Specific Yield | {result.specific_yield_kwh_kwp:.0f} kWh/kWp |
| Performance Ratio | {result.performance_ratio:.1f}% |
| Capacity Factor | {result.capacity_factor:.1f}% |

### Monthly Production (kWh)
| Month | Energy |
|-------|--------|
"""
        for month, energy in result.monthly_energy.items():
            report += f"| {month} | {energy:,.0f} |\n"
        
        report += f"""
### System Losses
"""
        for loss_type, loss_pct in result.losses.items():
            report += f"- **{loss_type.title()}:** {loss_pct}%\n"
        
        report += f"""
---

## 4. Financial Analysis

**Agent:** FinancialAgent

### Economic Assumptions
- Electricity Rate: ${financial['economic_assumptions']['electricity_rate_per_kwh']:.2f}/kWh
- System Cost: ${financial['economic_assumptions']['system_cost_per_watt']:.2f}/W
- Discount Rate: {financial['economic_assumptions']['discount_rate']*100:.0f}%
- Analysis Period: {financial['economic_assumptions']['analysis_period_years']} years

### Financial Metrics
| Metric | Value |
|--------|-------|
| Total System Cost | **${financial['financial_metrics']['total_system_cost_usd']:,.0f}** |
| Annual Savings | ${financial['financial_metrics']['annual_savings_usd']:,.0f} |
| Simple Payback | {financial['financial_metrics']['simple_payback_years']:.1f} years |
| Net Present Value | ${financial['financial_metrics']['net_present_value_usd']:,.0f} |
| LCOE | ${financial['financial_metrics']['lcoe_per_kwh']:.3f}/kWh |
| Estimated IRR | {financial['financial_metrics']['irr_estimate_percent']:.1f}% |

**Agent Insight:** {financial.get('llm_insight', 'N/A').split(chr(10))[0][:200]}...

---

## 5. LLM Consensus & Recommendations

_This section represents the collective reasoning of all agents._

"""
        
        return report


# ============== Coordinator ==============

class PVSystemCoordinator:
    """Main coordinator that orchestrates all agents"""
    
    def __init__(self, model: str = "gemma4:e4b"):
        self.model = model
        self.geo_agent = GeolocationAgent(model)
        self.weather_agent = WeatherAgent(model)
        self.design_agent = SystemDesignAgent(model)
        self.calculator = CalculationEngine()
        self.financial_agent = FinancialAgent(model)
        self.report_agent = ReportAgent(model)
        
    def run_simulation(self, specs: PVSystemSpecs) -> Dict:
        """Run full simulation with all agents"""
        
        print("=" * 60)
        print(f"PV SYSTEM SIMULATION - Multi-Agent System")
        print(f"Target: {specs.system_capacity_kw}kW system at {specs.latitude:.4f}, {specs.longitude:.4f}")
        print("=" * 60)
        print()
        
        # Step 1: Geolocation Analysis
        print("─" * 40)
        print("STEP 1: Geospatial Analysis")
        print("─" * 40)
        geo_analysis = self.geo_agent.analyze_location(specs)
        print()
        
        # Step 2: Weather Data
        print("─" * 40)
        print("STEP 2: Meteorological Data")
        print("─" * 40)
        weather = self.weather_agent.fetch_weather_data(specs)
        print()
        
        # Step 3: System Design
        print("─" * 40)
        print("STEP 3: System Design")
        print("─" * 40)
        design = self.design_agent.design_system(specs)
        print()
        
        # Step 4: Energy Simulation
        print("─" * 40)
        print("STEP 4: Energy Production Simulation")
        print("─" * 40)
        result = self.calculator.simulate_annual_production(specs, weather, design)
        print()
        
        # Step 5: Financial Analysis
        print("─" * 40)
        print("STEP 5: Financial Analysis")
        print("─" * 40)
        financial = self.financial_agent.analyze(specs, result, design)
        print()
        
        # Step 6: Generate Report
        print("─" * 40)
        print("STEP 6: Report Generation")
        print("─" * 40)
        report = self.report_agent.generate_markdown_report(
            specs, geo_analysis, design, result, financial
        )
        print()
        
        # Summary
        print("=" * 60)
        print("SIMULATION COMPLETE")
        print("=" * 60)
        print(f"\nAnnual Production: {result.annual_energy_kwh:,.0f} kWh")
        print(f"Performance Ratio: {result.performance_ratio:.1f}%")
        print(f"Simple Payback: {financial['financial_metrics']['simple_payback_years']:.1f} years")
        print(f"NPV: ${financial['financial_metrics']['net_present_value_usd']:,.0f}")
        
        return {
            "specs": specs,
            "geo_analysis": geo_analysis,
            "design": design,
            "result": result,
            "financial": financial,
            "report": report
        }


# ============== Main Entry Point ==============

def check_ollama():
    """Check if Ollama is running"""
    try:
        ollama.list()
        return True
    except:
        return False


def main():
    """Main function"""
    print("\n" + "=" * 60)
    print("  MULTI-AGENT PV SYSTEM CALCULATOR")
    print("  Powered by PVlib + Open LLMs")
    print("=" * 60 + "\n")
    
    # Check Ollama
    if not check_ollama():
        print("❌ Ollama not running!")
        print("Please start Ollama first: ollama serve")
        print("\nWithout Ollama, agents will use fallback reasoning.")
        print("(Install: curl -fsSL https://ollama.io/install.sh | sh)")
        print("(Then: ollama pull llama3.2)")
        print()
        use_llm = input("Continue without LLM reasoning? (y/n): ").lower() == 'y'
        if not use_llm:
            return
    else:
        print("✓ Ollama detected")
        models = ollama.list()
        available_models = [m['model'] for m in models.get('models', [])]
        print(f"Available models: {available_models}")
        
        if 'llama3.2:1b' not in available_models:
            print("\n⚠ llama3.2:1b not found. Pull it with: ollama pull llama3.2:1b")
            print("Continuing with available models...")
    
    print("\n" + "-" * 60)
    
    # Default: Politeknik Energi dan Pertambangan Bandung, West Java, Indonesia
    specs = PVSystemSpecs(
        latitude=-6.9147,           # Bandung, West Java (Southern hemisphere)
        longitude=107.6098,         # East longitude
        altitude=768,               # Bandung elevation
        timezone='Asia/Jakarta',    # WIB - Western Indonesia Time
        system_capacity_kw=10.0,
        module_type='standard',
        tilt=None,                  # Auto-calculate: ~6.9° facing north
        azimuth=0.0                 # North facing (for southern hemisphere)
    )
    
    # Optional: Get user input
    print("\n🌏 Default simulation: 10kW system at Politeknik Energi dan Pertambangan Bandung")
    print("   Location: Bandung, West Java, Indonesia")
    print("   Coordinates: -6.9147°, 107.6098° (Southern Hemisphere, High Elevation)")
    print("\nNote: In southern hemisphere, optimal azimuth is 0° (North), not 180°")
    
    # Auto-run for non-interactive mode, or ask user
    try:
        custom = input("Use custom location? (y/n) [n]: ").lower() == 'y'
    except:
        custom = False  # Non-interactive mode
    
    if custom:
        try:
            specs.latitude = float(input("Latitude (e.g., 33.4484): ") or specs.latitude)
            specs.longitude = float(input("Longitude (e.g., -112.0740): ") or specs.longitude)
            specs.system_capacity_kw = float(input("System size (kW, e.g., 10): ") or specs.system_capacity_kw)
            specs.azimuth = float(input("Azimuth (° from N, 180=South): ") or specs.azimuth)
        except:
            print("Using defaults due to input error.")
    
    # Run simulation
    print("\n")
    coordinator = PVSystemCoordinator()
    output = coordinator.run_simulation(specs)
    
    # Save report
    report_path = "pv_simulation_report.md"
    with open(report_path, 'w') as f:
        f.write(output['report'])
    
    print(f"\n\n✓ Report saved to: {report_path}")
    
    # Show sample hourly output
    print("\n" + "-" * 40)
    print("Sample Hourly Output (first 10 hours):")
    print("-" * 40)
    result = output['result']
    sample = result.hourly_output.head(10)
    for timestamp, power in sample.items():
        print(f"  {timestamp}: {power:.2f} kW")


if __name__ == "__main__":
    main()
