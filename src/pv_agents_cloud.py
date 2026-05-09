#!/usr/bin/env python3
"""
Multi-Agent PV System Calculator with Cloud LLM Support
Supports both local Ollama and cloud providers (OpenRouter, Ollama Cloud)
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

# LLM imports - support multiple providers
try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False

try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


# ============== Configuration ==============

class LLMProvider:
    """Unified interface for multiple LLM providers"""
    
    def __init__(self, provider: str = "ollama", model: str = "gemma4:e4b", api_key: str = None, base_url: str = None):
        """
        LLM Provider with unified interface.
        
        Local (Ollama) defaults: gemma4:e4b
        Cloud (OpenRouter/Ollama Cloud) defaults: qwen3.6:latest
        """
        self.provider = provider
        self.model = model
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
        self.base_url = base_url or os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
        
        if provider == "openrouter" and not self.api_key:
            raise ValueError("OPENROUTER_API_KEY environment variable required for OpenRouter")
        
        if provider == "openai" and not self.api_key:
            raise ValueError("OPENAI_API_KEY environment variable required for OpenAI")
    
    def chat(self, messages: List[Dict], temperature: float = 0.3) -> str:
        """Send chat request and return response"""
        
        if self.provider == "ollama":
            return self._ollama_chat(messages, temperature)
        elif self.provider in ["openrouter", "openai"]:
            return self._openai_compat_chat(messages, temperature)
        else:
            raise ValueError(f"Unknown provider: {self.provider}")
    
    def _ollama_chat(self, messages: List[Dict], temperature: float) -> str:
        """Local Ollama chat"""
        if not OLLAMA_AVAILABLE:
            return "[Error: ollama package not installed]"
        
        try:
            response = ollama.chat(
                model=self.model,
                messages=messages,
                options={"temperature": temperature}
            )
            return response['message']['content']
        except Exception as e:
            return f"[LLM Error: {e}]"
    
    def _openai_compat_chat(self, messages: List[Dict], temperature: float) -> str:
        """OpenAI-compatible API (OpenRouter, Ollama Cloud, etc.)"""
        if not OPENAI_AVAILABLE:
            return "[Error: openai package not installed. Run: pip install openai]"
        
        try:
            client = openai.OpenAI(
                api_key=self.api_key,
                base_url=self.base_url
            )
            
            response = client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=2048
            )
            
            return response.choices[0].message.content
        except Exception as e:
            return f"[LLM Error: {e}]"


# ============== Data Structures ==============

@dataclass
class PVSystemSpecs:
    """PV System Specifications - Default: Politeknik Energi dan Pertambangan Bandung"""
    # Location: Politeknik Energi dan Pertambangan Bandung, West Java, Indonesia
    latitude: float = -6.9147      # Bandung, West Java (Southern hemisphere)
    longitude: float = 107.6098    # East longitude
    altitude: float = 768.0        # Bandung elevation ~768m
    timezone: str = 'Asia/Jakarta'  # Western Indonesia Time (WIB)
    system_capacity_kw: float = 10.0
    module_type: str = 'standard_mono'
    module_power: float = 450.0  # Watts
    tilt: Optional[float] = None  # Auto-calculate if None
    azimuth: float = 0.0  # North facing (for Southern hemisphere)
    inverter_efficiency: float = 0.96
    dc_ac_ratio: float = 1.2
    
    def __post_init__(self):
        if self.tilt is None:
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
    """Base class for PV system agents with cloud LLM support"""
    
    def __init__(self, name: str, llm_provider: LLMProvider = None):
        self.name = name
        self.llm = llm_provider or LLMProvider(provider="ollama", model="gemma4:e4b")
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
            response = self.llm.chat(
                messages=[
                    {"role": "system", "content": "You are a PV system engineering AI agent."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3
            )
            return response
        except Exception as e:
            return f"[LLM Error: {e}] - Proceeding with default values."
    
    def log(self, message: str):
        """Log agent activity"""
        print(f"[{self.name}] {message}")


# ============== Specialized Agents ==============

class GeolocationAgent(PVAgent):
    """Agent for geospatial calculations and solar geometry"""
    
    def __init__(self, llm_provider: LLMProvider = None):
        super().__init__("GeolocationAgent", llm_provider)
    
    def analyze_location(self, specs: PVSystemSpecs) -> Dict:
        """Calculate solar geometry and optimal parameters"""
        self.log(f"Analyzing location: {specs.latitude:.4f}°, {specs.longitude:.4f}°")
        
        loc = location.Location(
            latitude=specs.latitude, 
            longitude=specs.longitude,
            altitude=specs.altitude,
            tz=specs.timezone
        )
        
        times = pd.date_range(
            start='2024-01-01', 
            end='2024-12-31 23:00', 
            freq='h',
            tz=specs.timezone
        )
        
        solar_pos = loc.get_solarposition(times)
        
        months = range(1, 13)
        optimal_tilts = []
        
        for month in months:
            month_days = solar_pos[solar_pos.index.month == month]
            noon_elevations = month_days.groupby(month_days.index.day)['elevation'].max()
            avg_elevation = noon_elevations.mean()
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
            "suggested_azimuth": 180 if specs.latitude > 0 else 0
        }
        
        llm_insight = self.think(
            "Recommend optimal tilt and azimuth for this location, considering seasonal sun angles and practical constraints.",
            analysis
        )
        analysis['llm_insight'] = llm_insight
        
        return analysis


class WeatherAgent(PVAgent):
    """Agent for fetching and processing meteorological data"""
    
    def __init__(self, llm_provider: LLMProvider = None):
        super().__init__("WeatherAgent", llm_provider)
        
    def fetch_weather_data(self, specs: PVSystemSpecs) -> WeatherData:
        """Fetch typical meteorological year data"""
        self.log(f"Fetching weather data for coordinates: {specs.latitude}, {specs.longitude}")
        
        weather = WeatherData()
        
        try:
            import openmeteo_requests
            import niquests
            
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
        """Generate representative synthetic weather data"""
        self.log("Generating representative TMY data...")
        
        times = pd.date_range('2024-01-01', periods=8760, freq='h', tz=specs.timezone)
        
        weather = WeatherData()
        weather.times = times
        
        day_of_year = times.dayofyear
        hour = times.hour
        
        annual_factor = 1 + 0.3 * np.sin((day_of_year - 15) * 2 * np.pi / 365 - np.pi/2)
        solar_time = hour + (specs.longitude % 15) / 15
        daily_factor = np.maximum(0, np.sin((solar_time - 6) * np.pi / 12))
        
        peak_ghi = 1000
        weather.ghi = pd.Series(peak_ghi * annual_factor * daily_factor, index=times)
        weather.dni = weather.ghi * 0.8
        weather.dhi = weather.ghi * 0.3
        
        weather.temp_air = pd.Series(
            20 + 15 * np.sin((day_of_year - 15) * 2 * np.pi / 365) + 
            5 * np.sin((hour - 14) * np.pi / 12),
            index=times
        )
        
        weather.wind_speed = pd.Series(3.0, index=times)
        
        return weather


class SystemDesignAgent(PVAgent):
    """Agent for PV system design and component sizing"""
    
    def __init__(self, llm_provider: LLMProvider = None):
        super().__init__("SystemDesignAgent", llm_provider)
        self.module_db = self._load_module_database()
        self.inverter_db = self._load_inverter_database()
    
    def _load_module_database(self) -> Dict:
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
        return {
            'string_10kw': {'pac0': 10000, 'pdc0': 11000, 'eta_inv_nom': 0.97},
            'string_15kw': {'pac0': 15000, 'pdc0': 16500, 'eta_inv_nom': 0.975},
            'hybrid_10kw': {'pac0': 10000, 'pdc0': 13000, 'eta_inv_nom': 0.98}
        }
    
    def design_system(self, specs: PVSystemSpecs) -> Dict:
        """Design PV system configuration"""
        self.log(f"Designing {specs.system_capacity_kw}kW system")
        
        module = self.module_db.get(specs.module_type, self.module_db['standard_mono'])
        
        num_modules = int(np.ceil(specs.system_capacity_kw * 1000 / module['pdc0']))
        actual_capacity = num_modules * module['pdc0'] / 1000
        
        modules_per_string = min(24, int(1000 / module['v_oc']))
        num_strings = int(np.ceil(num_modules / modules_per_string))
        actual_modules = modules_per_string * num_strings
        actual_capacity = actual_modules * module['pdc0'] / 1000
        
        if actual_capacity <= 12:
            inverter_name = 'string_10kw'
        elif actual_capacity <= 17:
            inverter_name = 'string_15kw'
        else:
            inverter_name = 'string_15kw'
        
        inverter = self.inverter_db[inverter_name]
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
            "module_model": specs.module_type,
            "inverter_specifications": inverter,
            "inverter_model": inverter_name,
            "array_configuration": {
                "tilt_degrees": specs.tilt,
                "azimuth_degrees": specs.azimuth,
                "ground_coverage_ratio": 0.4
            }
        }
        
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
        """Run annual energy simulation using the canonical engine."""
        print(f"[{self.name}] Running annual simulation...")

        try:
            from simulation import simulate_pv_system as _simulate
        except ImportError:
            from .simulation import simulate_pv_system as _simulate

        weather_df = pd.DataFrame(
            {
                "ghi": weather.ghi,
                "dni": weather.dni,
                "dhi": weather.dhi,
                "temp_air": weather.temp_air,
                "wind_speed": getattr(weather, "wind_speed", 1.0),
            },
            index=weather.times,
        )

        module_params = design['module_specifications']
        actual_capacity = design['system_summary']['actual_capacity_kw']
        sim_specs = {
            "latitude": specs.latitude,
            "longitude": specs.longitude,
            "altitude": specs.altitude,
            "timezone": specs.timezone,
            "tilt": specs.tilt,
            "azimuth": specs.azimuth,
            "system_capacity_kw": actual_capacity,
            "module_power": module_params.get("pdc0", 450),
            "gamma_pdc": module_params.get("gamma_pdc", -0.003),
            "inverter_efficiency": specs.inverter_efficiency,
            "ac_capacity_kw": design["inverter_specifications"]["pac0"] / 1000,
        }

        out = _simulate(sim_specs, weather_df)

        return SimulationResult(
            annual_energy_kwh=out["annual_kwh"],
            specific_yield_kwh_kwp=out["specific_yield"],
            performance_ratio=out["performance_ratio"],
            capacity_factor=out["capacity_factor"],
            hourly_output=out["hourly_output"],
            monthly_energy=out["monthly_kwh"],
        )


class FinancialAgent(PVAgent):
    """Agent for financial analysis"""
    
    def __init__(self, llm_provider: LLMProvider = None):
        super().__init__("FinancialAgent", llm_provider)
    
    def analyze(self, specs: PVSystemSpecs, results: SimulationResult, design: Dict) -> Dict:
        """Calculate financial metrics"""
        self.log("Calculating financial metrics...")
        
        cost_per_watt = 2.50
        electricity_rate = 0.13
        discount_rate = 0.05
        years = 25
        degradation = 0.005
        
        system_cost = design['system_summary']['actual_capacity_kw'] * 1000 * cost_per_watt
        annual_savings = results.annual_energy_kwh * electricity_rate
        
        payback = system_cost / annual_savings if annual_savings > 0 else float('inf')
        
        npv = -system_cost
        for year in range(1, years + 1):
            production = results.annual_energy_kwh * ((1 - degradation) ** year)
            npv += (production * electricity_rate) / ((1 + discount_rate) ** year)
        
        lifetime_production = sum(
            results.annual_energy_kwh * ((1 - degradation) ** y) for y in range(years)
        )
        lcoe = system_cost / lifetime_production if lifetime_production > 0 else float('inf')
        
        financial = {
            "system_cost": system_cost,
            "annual_savings": annual_savings,
            "simple_payback_years": payback,
            "npv_25yr": npv,
            "lcoe": lcoe,
            "irr_approx": (annual_savings / system_cost) * 100 if system_cost > 0 else 0
        }
        
        llm_insight = self.think(
            "Analyze the financial viability of this PV system. Consider local electricity rates, incentives, and ROI.",
            {**financial, "annual_production_kwh": results.annual_energy_kwh}
        )
        financial['llm_insight'] = llm_insight
        
        return financial


class ReportAgent(PVAgent):
    """Agent for generating reports"""
    
    def __init__(self, llm_provider: LLMProvider = None):
        super().__init__("ReportAgent", llm_provider)
    
    def generate(self, specs: PVSystemSpecs, geo: Dict, design: Dict, 
                results: SimulationResult, financial: Dict) -> str:
        """Generate final report"""
        self.log("Generating report...")
        
        hemisphere = "Southern" if specs.latitude < 0 else "Northern"
        facing = "North" if specs.latitude < 0 else "South"
        
        report = f"""
╔══════════════════════════════════════════════════════════════════╗
║           PV SYSTEM ANALYSIS REPORT                               ║
╠══════════════════════════════════════════════════════════════════╣
║  Location: {specs.latitude:.4f}°N, {abs(specs.longitude):.4f}°{'W' if specs.longitude < 0 else 'E':<38} ║
║  Hemisphere: {hemisphere:<52} ║
╠══════════════════════════════════════════════════════════════════╣

📍 LOCATION ANALYSIS
─────────────────────────────────────────────────────────────────
Max Sun Elevation: {geo['annual_sun_path']['max_solar_elevation']:.1f}°
Recommended Tilt: {geo['recommended_fixed_tilt']:.1f}° ({facing}-facing)
Climate: {'Tropical' if abs(specs.latitude) < 25 else 'Temperate'}

⚙️  SYSTEM DESIGN
─────────────────────────────────────────────────────────────────
DC Capacity:      {design['system_summary']['actual_capacity_kw']:.1f} kW
AC Capacity:      {design['inverter_specifications']['pac0'] / 1000:.1f} kW
DC/AC Ratio:      {design['system_summary']['dc_ac_ratio']:.2f}
Modules:          {design['system_summary']['num_modules']} × {design['module_specifications']['pdc0']}W
Inverter:         {design['inverter_model'].replace('_', ' ').title()}

⚡ ENERGY PRODUCTION
─────────────────────────────────────────────────────────────────
Annual Production:    {results.annual_energy_kwh:>10,.0f} kWh/year
Specific Yield:       {results.specific_yield_kwh_kwp:>10,.0f} kWh/kWp/year
Performance Ratio:   {results.performance_ratio:>10.1f}%
Capacity Factor:     {results.capacity_factor:>10.1f}%
Peak Output:          {results.hourly_output.max():>10.1f} kW

Monthly Production (kWh):
"""
        for month, energy in results.monthly_energy.items():
            report += f"  {month}: {energy:>8,.0f}"
            if list(results.monthly_energy.keys()).index(month) % 3 == 2:
                report += "\n"
        
        report += f"""
💰 FINANCIAL ANALYSIS
─────────────────────────────────────────────────────────────────
System Cost:          ${financial['system_cost']:>10,.0f}
Annual Savings:       ${financial['annual_savings']:>10,.0f}/year
Simple Payback:       {financial['simple_payback_years']:>10.1f} years
LCOE:                 ${financial['lcoe']:>10.3f}/kWh
NPV (25yr):           ${financial['npv_25yr']:>10,.0f}

╔══════════════════════════════════════════════════════════════════╗
║  Multi-Agent AI System: GeoLocation → Weather → Design          ║
║                         → Calculation → Financial → Report      ║
║  LLM Provider: {self.llm.provider:<52} ║
╚══════════════════════════════════════════════════════════════════╝
"""
        return report


# ============== Main System ==============

class PVMultiAgentSystem:
    """Main orchestrator for the multi-agent PV system"""
    
    def __init__(self, llm_provider: LLMProvider = None):
        self.llm = llm_provider or LLMProvider(provider="ollama", model="gemma4:e4b")
        
        self.geo_agent = GeolocationAgent(self.llm)
        self.weather_agent = WeatherAgent(self.llm)
        self.design_agent = SystemDesignAgent(self.llm)
        self.calc_engine = CalculationEngine()
        self.financial_agent = FinancialAgent(self.llm)
        self.report_agent = ReportAgent(self.llm)
    
    def run_simulation(self, specs: PVSystemSpecs = None) -> Dict:
        """Run complete multi-agent simulation"""
        if specs is None:
            specs = PVSystemSpecs()
        
        print("\n" + "=" * 70)
        print("  🤖 MULTI-AGENT PV SYSTEM CALCULATOR")
        print(f"  ☁️  LLM Provider: {self.llm.provider} | Model: {self.llm.model}")
        print("=" * 70 + "\n")
        
        # Step 1: Geolocation analysis
        geo_analysis = self.geo_agent.analyze_location(specs)
        
        # Step 2: Weather data
        weather = self.weather_agent.fetch_weather_data(specs)
        
        # Step 3: System design
        design = self.design_agent.design_system(specs)
        
        # Step 4: Energy simulation
        results = self.calc_engine.simulate_annual_production(specs, weather, design)
        
        # Step 5: Financial analysis
        financial = self.financial_agent.analyze(specs, results, design)
        
        # Step 6: Generate report
        report = self.report_agent.generate(specs, geo_analysis, design, results, financial)
        
        print("\n" + report)
        
        return {
            'specs': specs,
            'geo_analysis': geo_analysis,
            'design': design,
            'results': results,
            'financial': financial,
            'report': report
        }


# ============== CLI Entry Point ==============

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Multi-Agent PV System Calculator")
    parser.add_argument("--provider", choices=["ollama", "openrouter", "openai"], 
                       default="ollama", help="LLM provider")
    parser.add_argument("--model", default="gemma4:e4b", 
                       help="Model name. Local: gemma4:e4b, qwen2.5:7b. Cloud (Ollama): qwen3.6:latest, gemma2:9b")
    parser.add_argument("--api-key", help="API key (or set OPENROUTER_API_KEY env var)")
    parser.add_argument("--base-url", help="API base URL (for OpenRouter)")
    parser.add_argument("--latitude", type=float, default=-6.9147, help="Latitude")
    parser.add_argument("--longitude", type=float, default=107.6098, help="Longitude")
    parser.add_argument("--capacity", type=float, default=10.0, help="System capacity (kW)")
    
    args = parser.parse_args()
    
    # Create LLM provider
    llm = LLMProvider(
        provider=args.provider,
        model=args.model,
        api_key=args.api_key,
        base_url=args.base_url
    )
    
    # Create system specs
    specs = PVSystemSpecs(
        latitude=args.latitude,
        longitude=args.longitude,
        system_capacity_kw=args.capacity
    )
    
    # Run simulation
    system = PVMultiAgentSystem(llm_provider=llm)
    system.run_simulation(specs)


if __name__ == "__main__":
    main()
