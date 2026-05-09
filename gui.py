#!/usr/bin/env python3
"""
Streamlit GUI for Multi-Agent PV System Calculator
Run with: streamlit run gui.py
"""

import os
import sys
import json
import base64
from io import BytesIO
from datetime import datetime, timedelta
from typing import Dict, Any

import streamlit as st
import pandas as pd
import numpy as np
import pvlib
from pvlib import location, irradiance

# Add project paths for module discovery
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _PROJECT_ROOT)
sys.path.insert(0, os.path.join(_PROJECT_ROOT, "src"))
sys.path.insert(0, os.path.join(_PROJECT_ROOT, "data"))

# Import PV module database
from pv_module_database import (
    PV_MODULE_DATABASE,
    get_manufacturers,
    get_module_names_by_manufacturer,
    get_module_by_name,
    module_to_dict,
)

# Canonical simulation engine
from simulation import simulate_pv_system, LossModel

# Real-weather provider (Open-Meteo) with synthetic fallback
from weather_provider import fetch_weather_or_fallback

# Dynamic module fetcher (fetches from live sources)
try:
    from module_fetcher import fetch_all_modules, get_module_statistics

    DYNAMIC_FETCHER_AVAILABLE = True
except ImportError:
    DYNAMIC_FETCHER_AVAILABLE = False

# LLM imports
try:
    from pv_agents_cloud import LLMProvider

    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False

# PDF imports — try direct import first (when running as package), then file-based fallback (Streamlit standalone)
import warnings
_pdf_gen_path = os.path.join(_PROJECT_ROOT, "src", "pdf_generator.py")
PDF_AVAILABLE = False
try:
    from pdf_generator import generate_pv_report_pdf, generate_ai_analysis_pdf
    PDF_AVAILABLE = True
except ImportError:
    # Streamlit or other runtime where sys.path lacks src/ — load explicitly
    try:
        import importlib.util
        if not os.path.exists(_pdf_gen_path):
            raise FileNotFoundError(f"pdf_generator.py not found at {_pdf_gen_path}")
        _pdf_spec = importlib.util.spec_from_file_location("pdf_generator", _pdf_gen_path)
        if _pdf_spec is None or _pdf_spec.loader is None:
            raise ImportError(f"Could not load module spec from {_pdf_gen_path}")
        _pdf_module = importlib.util.module_from_spec(_pdf_spec)
        _pdf_spec.loader.exec_module(_pdf_module)
        generate_pv_report_pdf = _pdf_module.generate_pv_report_pdf
        generate_ai_analysis_pdf = _pdf_module.generate_ai_analysis_pdf
        PDF_AVAILABLE = True
    except Exception as _pdf_err:
        warnings.warn(f"PDF generator import failed: {type(_pdf_err).__name__}: {_pdf_err}")
        generate_pv_report_pdf = None
        generate_ai_analysis_pdf = None

# Storage & Self-Consumption imports
try:
    sys.path.insert(0, os.path.join(_PROJECT_ROOT, "src"))
    from storage_engine import BatterySpecs, BatterySimulator
    from storage_optimizer import self_consumption_optimizer, StorageScenario
    from load_profiles import generate_profile
    from pln_tariffs import list_tariffs, get_tariff, PLN_TARIFFS
    from pv_agents import StorageCoordinator
    STORAGE_AVAILABLE = True
except Exception as _stor_err:
    STORAGE_AVAILABLE = False
    import warnings
    warnings.warn(f"Storage module import failed: {_stor_err}")

###############################################################################
# Page config
###############################################################################
st.set_page_config(
    page_title="Sunnyside AI | PV Simulator",
    page_icon="🌅",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS
st.markdown("""
<style>
    body {
        background-color: #111827;
    }
    .main-header {
        font-size: 3.5rem;
        font-weight: 800;
        color: #00d4ff;
        text-align: center;
        margin-bottom: 0.5rem;
        letter-spacing: -0.02em;
        text-shadow: 0 0 20px rgba(0, 212, 255, 0.3);
    }
    .tagline {
        font-size: 1.2rem;
        color: #9ca3af;
        text-align: center;
        margin-bottom: 2rem;
        letter-spacing: 0.02em;
    }
    .logo-box {
        display: flex;
        justify-content: center;
        align-items: center;
        gap: 0.75rem;
        margin-bottom: 0.5rem;
    }
    .logo-icon {
        width: 48px;
        height: 48px;
        border-radius: 12px;
        background: linear-gradient(to bottom, #f59e0b 50%, #3b82f6 50%);
        box-shadow: 0 0 15px rgba(245, 158, 11, 0.4);
    }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 0.5rem;
        color: white;
        text-align: center;
    }
    .stAlert {
        border-radius: 0.5rem;
    }
</style>
""", unsafe_allow_html=True)

# ============== Helper Functions ==============

def calculate_solar_position(latitude: float, longitude: float, timezone: str, 
                            date: datetime) -> Dict:
    """Calculate solar position for given location and date"""
    loc = location.Location(latitude, longitude, tz=timezone)
    times = pd.date_range(date.replace(hour=0), periods=24, freq='h', tz=timezone)
    solpos = loc.get_solarposition(times)
    return {
        'max_elevation': solpos['elevation'].max(),
        'min_elevation': solpos['elevation'].min(),
        'sunrise': times[solpos['elevation'] > 0][0] if any(solpos['elevation'] > 0) else None,
        'sunset': times[solpos['elevation'] > 0][-1] if any(solpos['elevation'] > 0) else None,
    }


def generate_synthetic_weather(specs: Dict, periods: int = 8760) -> pd.DataFrame:
    """Generate synthetic TMY weather data"""
    timezone = specs.get('timezone', 'Asia/Jakarta')
    times = pd.date_range('2024-01-01', periods=periods, freq='h', tz=timezone)
    
    idx = np.arange(periods)
    day_of_year = idx % 365 + 1
    hour = idx % 24
    
    # Seasonal variation
    seasonal = 1 + 0.35 * np.sin((day_of_year - 15) * 2 * np.pi / 365 - np.pi/2)
    
    # Daily pattern
    utc_offset = 7  # WIB
    local_hour = (hour + utc_offset) % 24
    daily = np.maximum(0, np.sin((local_hour - 6) * np.pi / 12))
    
    # Weather noise
    np.random.seed(42)
    cloud_factor = np.random.beta(2, 2, size=periods) * 0.3 + 0.7
    
    # GHI
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
    temp_air = temp_base + temp_daily + np.random.normal(0, 2, periods)
    
    # Wind
    wind_speed = np.maximum(0, 3 + np.random.normal(0, 1.5, periods))
    
    weather = pd.DataFrame({
        'ghi': ghi,
        'dni': dni,
        'dhi': dhi,
        'temp_air': temp_air,
        'wind_speed': wind_speed
    }, index=times)
    
    return weather


# `simulate_pv_system` is re-exported from `simulation` (imported above).


def generate_report(specs: Dict, results: Dict, solar: Dict) -> str:
    """Generate text report"""
    report = f"""
╔══════════════════════════════════════════════════════════════════╗
║           PV SYSTEM ANALYSIS REPORT                               ║
╠══════════════════════════════════════════════════════════════════╣
║  Location: {specs.get('name', 'Custom Location'):<50} ║
║  Coordinates: {specs['latitude']:.4f}°N, {abs(specs['longitude']):.4f}°{'W' if specs['longitude'] < 0 else 'E':<35} ║
╠══════════════════════════════════════════════════════════════════╣

📍 LOCATION ANALYSIS
─────────────────────────────────────────────────────────────────
Max Sun Elevation: {solar['max_elevation']:.1f}°
Climate Zone: {'Tropical' if abs(specs['latitude']) < 25 else 'Temperate'}
Recommended Tilt: {specs.get('tilt', abs(specs['latitude'])):.1f}°
Array Azimuth: {specs.get('azimuth', 0):.0f}° ({'North' if specs['latitude'] < 0 else 'South'}-facing)

⚙️  SYSTEM DESIGN
─────────────────────────────────────────────────────────────────
DC Capacity:      {results['dc_capacity_kw']:.1f} kW
AC Capacity:      {results['ac_capacity_kw']:.1f} kW
Total Modules:    {results['num_modules']}
Module Type:      {specs.get('module_type', 'standard_mono').replace('_', ' ').title()}

⚡ ENERGY PRODUCTION
─────────────────────────────────────────────────────────────────
Annual Production:    {results['annual_kwh']:>10,.0f} kWh/year
Specific Yield:       {results['specific_yield']:>10,.0f} kWh/kWp/year
Performance Ratio:   {results['performance_ratio']:>10.1f}%
Capacity Factor:     {results['capacity_factor']:>10.1f}%
Peak Output:          {results['peak_power_kw']:>10.1f} kW

💰 FINANCIAL ANALYSIS
─────────────────────────────────────────────────────────────────
System Cost:          ${results['system_cost']:>10,.0f}
Annual Savings:       ${results['annual_savings']:>10,.0f}/year
Simple Payback:       {results['payback_years']:>10.1f} years
LCOE:                 ${results['lcoe']:>10.3f}/kWh

╔══════════════════════════════════════════════════════════════════╗
║  Powered by PVlib Python + Multi-Agent AI Architecture           ║
╚══════════════════════════════════════════════════════════════════╝
"""
    return report


def create_llm_provider(provider: str, model: str, api_key: str = None, base_url: str = None):
    """Factory for LLM provider"""
    if not LLM_AVAILABLE:
        return None
    return LLMProvider(provider=provider, model=model, api_key=api_key, base_url=base_url)


def generate_pv_context(specs: dict, results: dict) -> str:
    """Generate simulation context for LLM"""
    return f"""PV System Simulation Results:
Location: {specs.get('name', 'Unknown')} ({specs['latitude']:.4f}, {specs['longitude']:.4f})
System Capacity: {results['dc_capacity_kw']:.1f} kW DC / {results['ac_capacity_kw']:.1f} kW AC
Module Power: {specs.get('module_power', 450)}W x {results['num_modules']} modules
Tilt: {specs.get('tilt', 0):.1f} deg, Azimuth: {specs.get('azimuth', 0):.0f} deg
Annual Production: {results['annual_kwh']:,.0f} kWh
Specific Yield: {results['specific_yield']:.0f} kWh/kWp/year
Performance Ratio: {results['performance_ratio']:.1f}%
Capacity Factor: {results['capacity_factor']:.1f}%
Peak Output: {results['peak_power_kw']:.1f} kW
System Cost: ${results['system_cost']:,.0f}
Annual Savings: ${results['annual_savings']:,.0f}
Payback: {results['payback_years']:.1f} years
LCOE: ${results['lcoe']:.3f}/kWh
"""


# ============== Main App ==============

def main():
    # Header
    st.markdown("""
    <div style="text-align: center; margin-bottom: 2rem;">
        <div style="display: flex; align-items: center; justify-content: center; gap: 0.75rem; margin-bottom: 0.5rem;">
            <div style="width: 48px; height: 48px; border-radius: 12px; background: linear-gradient(to bottom, #f59e0b 50%, #3b82f6 50%); box-shadow: 0 0 15px rgba(245, 158, 11, 0.4);"></div>
            <span style="font-size: 3.5rem; font-weight: 800; color: #00d4ff; letter-spacing: -0.02em; text-shadow: 0 0 20px rgba(0, 212, 255, 0.3);">Sunnyside AI</span>
        </div>
        <div style="font-size: 1.2rem; color: #9ca3af; letter-spacing: 0.02em;">
            AI-powered solar simulation by Sunnyside AI — Physics meets Intelligence
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # Check for dynamic module database
    if DYNAMIC_FETCHER_AVAILABLE:
        with st.sidebar:
            st.info("🔄 Dynamic module database enabled")
            
            # Auto-fetch on first load
            if 'modules_loaded' not in st.session_state:
                with st.spinner("Fetching updated PV module database..."):
                    try:
                        modules = fetch_all_modules()
                        stats = get_module_statistics(modules)
                        st.session_state.modules_loaded = True
                        st.session_state.dynamic_modules = modules
                        st.session_state.module_stats = stats
                        st.success(f"✓ {stats['total_modules']} modules loaded")
                        st.caption(f"Source: {stats['source']} | Updated: {stats['last_updated'][:10]}")
                    except Exception as e:
                        st.warning(f"Using fallback database: {e}")
                        st.session_state.modules_loaded = True
                        st.session_state.dynamic_modules = None
            else:
                stats = st.session_state.get('module_stats', {})
                if stats:
                    st.success(f"✓ {stats['total_modules']} modules loaded")
                    st.caption(f"Source: {stats.get('source', 'N/A')}")
                
                # Refresh button
                if st.button("🔄 Refresh Module Database"):
                    with st.spinner("Fetching latest modules..."):
                        try:
                            modules = fetch_all_modules(force_refresh=True)
                            stats = get_module_statistics(modules)
                            st.session_state.dynamic_modules = modules
                            st.session_state.module_stats = stats
                            st.success(f"✓ Updated: {stats['total_modules']} modules")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Refresh failed: {e}")
    
    # Sidebar - Location Settings
    with st.sidebar:
        st.header("📍 Location")
        
        # Preset locations
        location_preset = st.selectbox(
            "Select Location",
            ["Custom", "Bandung, Indonesia", "Jakarta, Indonesia", 
             "Phoenix, USA", "Berlin, Germany", "Bikaner, India"]
        )
        
        if location_preset == "Custom":
            latitude = st.number_input("Latitude", value=-6.9147, step=0.0001)
            longitude = st.number_input("Longitude", value=107.6098, step=0.0001)
            location_name = st.text_input("Location Name", "Custom Location")
        elif location_preset == "Bandung, Indonesia":
            latitude = -6.9147
            longitude = 107.6098
            location_name = "Politeknik Energi dan Pertambangan Bandung"
        elif location_preset == "Jakarta, Indonesia":
            latitude = -6.2088
            longitude = 106.8456
            location_name = "Jakarta, Indonesia"
        elif location_preset == "Phoenix, USA":
            latitude = 33.4484
            longitude = -112.0740
            location_name = "Phoenix, Arizona"
        elif location_preset == "Berlin, Germany":
            latitude = 52.5200
            longitude = 13.4050
            location_name = "Berlin, Germany"
        elif location_preset == "Bikaner, India":
            latitude = 28.06
            longitude = 73.30
            location_name = "Engineering College Bikaner"
        
        timezone = st.selectbox(
            "Timezone",
            ["Asia/Jakarta", "US/Arizona", "Europe/Berlin", "Asia/Kolkata", "UTC"],
            index=0
        )
        altitude = st.number_input("Altitude (m)", value=768, step=10)

        st.subheader("Weather data")
        weather_source = st.radio(
            "Source",
            ["Open-Meteo (real)", "Synthetic TMY"],
            index=0,
            help="Real weather is fetched from Open-Meteo's free archive API "
                 "and cached locally. Synthetic TMY is generated from a simple "
                 "clear-sky model.",
        )
        weather_year = st.number_input(
            "Reference year",
            min_value=2000, max_value=2024, value=2023, step=1,
            disabled=(weather_source != "Open-Meteo (real)"),
        )

        st.header("⚙️ System Design")
        
        # Module selection from database
        st.subheader("PV Module Selection")
        
        # Option to use database or custom
        use_database = st.checkbox("Select from module database", value=True)
        
        if use_database:
            # Check if we have dynamic modules
            dynamic_modules = st.session_state.get('dynamic_modules', None)
            
            if dynamic_modules and len(dynamic_modules) > 0:
                # Use dynamic modules
                st.caption(f"📡 Live database: {len(dynamic_modules)} modules")
                
                # Get unique manufacturers from dynamic modules
                manufacturers = sorted(list(set(m['manufacturer'] for m in dynamic_modules)))
                
                # Manufacturer selection
                default_idx = manufacturers.index("LONGi Solar") if "LONGi Solar" in manufacturers else 0
                selected_manufacturer = st.selectbox(
                    "Manufacturer",
                    manufacturers,
                    index=default_idx
                )
                
                # Get models for selected manufacturer
                models = [m['model_name'] for m in dynamic_modules 
                         if m['manufacturer'] == selected_manufacturer]
                models = sorted(list(set(models)))
                
                # Model selection
                selected_model = st.selectbox(
                    "Model",
                    models
                )
                
                # Find the module in dynamic list
                selected_module = next(
                    (m for m in dynamic_modules 
                     if m['manufacturer'] == selected_manufacturer and m['model_name'] == selected_model),
                    None
                )
                
                if selected_module:
                    # Display module info
                    st.info(f"""
                    **{selected_manufacturer} {selected_model}**
                    - Power: {selected_module['pdc0']}W
                    - Efficiency: {selected_module['efficiency']:.1f}%
                    - Technology: {selected_module['technology']}
                    - Warranty: {selected_module.get('warranty_years', 25)} years
                    - Source: {selected_module.get('source', 'Unknown')}
                    """)
                    
                    module_type = selected_manufacturer.lower().replace(' ', '_') + '_' + selected_model.lower().replace(' ', '_')
                    module_power = selected_module['pdc0']
                    module_efficiency = selected_module['efficiency']
                    gamma_pdc = selected_module.get('gamma_pdc', -0.0035)
                else:
                    st.error("Module not found")
                    module_power = 450
                    module_efficiency = 21.0
                    gamma_pdc = -0.0035
            
            else:
                # Fall back to static database
                st.caption("📦 Using fallback database")
                
                # Get manufacturers
                manufacturers = get_manufacturers()
                
                # Manufacturer selection
                selected_manufacturer = st.selectbox(
                    "Manufacturer",
                    manufacturers,
                    index=manufacturers.index("LONGi Solar") if "LONGi Solar" in manufacturers else 0
                )
                
                # Get models for selected manufacturer
                models = get_module_names_by_manufacturer(selected_manufacturer)
                
                # Model selection
                selected_model = st.selectbox(
                    "Model",
                    models
                )
                
                # Get module specs
                try:
                    selected_module = get_module_by_name(selected_manufacturer, selected_model)
                    module_specs = module_to_dict(selected_module)
                    
                    # Display module info
                    st.info(f"""
                    **{selected_manufacturer} {selected_model}**
                    - Power: {selected_module.pdc0}W
                    - Efficiency: {selected_module.efficiency}%
                    - Technology: {selected_module.technology}
                    - Warranty: {selected_module.warranty_years} years
                    """)
                    
                    module_type = selected_manufacturer.lower().replace(' ', '_') + '_' + selected_model.lower().replace(' ', '_')
                    module_power = selected_module.pdc0
                    module_efficiency = selected_module.efficiency
                    gamma_pdc = selected_module.gamma_pdc
                    
                except Exception as e:
                    st.error(f"Error loading module: {e}")
                    module_power = 450
                    module_efficiency = 21.0
                    gamma_pdc = -0.0035
        else:
            # Custom module type
            module_type = st.selectbox(
                "Module Type",
                ["standard_mono", "standard_poly", "premium_mono"],
                format_func=lambda x: x.replace('_', ' ').title()
            )
            module_power = st.slider("Module Power (W)", 300, 600, 450, 10)
            module_efficiency = st.slider("Module Efficiency (%)", 15.0, 25.0, 21.0, 0.5)
            gamma_pdc = -0.0035
        
        system_capacity = st.slider("System Capacity (kW)", 1.0, 100.0, 10.0, 0.5)
        
        # Auto-calculate optimal tilt
        auto_tilt = st.checkbox("Auto-calculate optimal tilt", value=True)
        if auto_tilt:
            tilt = abs(latitude)
        else:
            tilt = st.slider("Tilt Angle (°)", 0, 90, int(abs(latitude)))
        
        # Auto-calculate azimuth based on hemisphere
        auto_azimuth = st.checkbox("Auto-calculate azimuth (hemisphere-aware)", value=True)
        if auto_azimuth:
            azimuth = 0 if latitude < 0 else 180
        else:
            azimuth = st.slider("Azimuth (°)", 0, 360, 0 if latitude < 0 else 180)
        
        st.header("💰 Financial")
        cost_per_watt = st.number_input("Cost ($/W)", value=2.50, step=0.10)
        electricity_rate = st.number_input("Electricity Rate ($/kWh)", value=0.13, step=0.01)

        # ====== BATTERY STORAGE SECTION ======
        st.markdown("---")
        st.header("🔋 Battery Storage + PLN Net Metering")

        enable_storage = st.checkbox("Enable Battery & Self-Consumption Analysis", value=False)

        if enable_storage and STORAGE_AVAILABLE:
            st.subheader("Customer Profile")
            sc_profile = st.selectbox(
                "Load Profile Type",
                ["residential", "commercial", "industrial"],
                format_func=lambda x: x.title(),
            )
            sc_annual_load = st.number_input(
                "Annual Load (kWh)", value=4380 if sc_profile == "residential" else (36500 if sc_profile == "commercial" else 350000), step=100
            )

            st.subheader("PLN Tariff")
            tariff_list = list(PLN_TARIFFS.keys())
            sc_tariff = st.selectbox(
                "Tariff Code",
                tariff_list,
                index=tariff_list.index("R-1/2200VA") if "R-1/2200VA" in tariff_list else 0,
            )
            t = get_tariff(sc_tariff)
            st.caption(f"Energy rate: Rp {t.energy_rate_idr_kwh:,.0f}/kWh | Fixed: Rp {t.fixed_charge_idr_month:,.0f}/mo")

            st.subheader("Battery Specs")
            batt_capacity = st.slider("Battery Capacity (kWh)", 1.0, 50.0, 10.0, 0.5)
            batt_charge = st.slider("Max Charge Power (kW)", 0.5, 25.0, 5.0, 0.5)
            batt_discharge = st.slider("Max Discharge Power (kW)", 0.5, 25.0, 5.0, 0.5)
        else:
            enable_storage = False

        st.markdown("---")
        st.header("🤖 AI Agent")

        enable_ai = st.checkbox("Enable AI Insights", value=True)
        ai_provider = None
        ai_model = None
        ai_api_key = None

        if enable_ai and LLM_AVAILABLE:
            ai_provider = st.selectbox(
                "LLM Provider",
                ["ollama", "openrouter", "openai"],
                format_func=lambda x: {"ollama": "🖥️ Ollama (Local)", "openrouter": "☁️ OpenRouter (Cloud)", "openai": "☁️ OpenAI"}.get(x, x)
            )

            if ai_provider == "ollama":
                ai_model = st.text_input("Model", "gemma4:e4b")
            elif ai_provider == "openrouter":
                ai_model = st.text_input("Model", "qwen3.6:latest")
                ai_api_key = st.text_input("API Key", type="password", value=os.getenv("OPENROUTER_API_KEY", ""))
            elif ai_provider == "openai":
                ai_model = st.text_input("Model", "gpt-3.5-turbo")
                ai_api_key = st.text_input("API Key", type="password", value=os.getenv("OPENAI_API_KEY", ""))
        elif enable_ai and not LLM_AVAILABLE:
            st.warning("⚠️ LLM module not available. Install deps: pip install ollama openai")

        # Store specs
        specs = {
            'name': location_name,
            'latitude': latitude,
            'longitude': longitude,
            'altitude': altitude,
            'timezone': timezone,
            'system_capacity_kw': system_capacity,
            'module_type': module_type,
            'module_power': module_power,
            'module_efficiency': module_efficiency,
            'gamma_pdc': gamma_pdc,
            'tilt': tilt,
            'azimuth': azimuth,
            'inverter_efficiency': 0.96,
            'cost_per_watt': cost_per_watt,
            'electricity_rate': electricity_rate
        }

        # AI button in sidebar
        ai_clicked = False
        if enable_ai and LLM_AVAILABLE:
            ai_clicked = st.button("🚀 Generate AI Insights", type="primary", use_container_width=True)

        # ========== PDF REPORT SECTION ==========
        st.markdown("---")
        st.header("📄 PDF Report")

        # PDF customization inputs
        pdf_company = st.text_input("Company Name", "", key="pdf_company")
        pdf_author = st.text_input("Prepared By", "", key="pdf_author")
        pdf_logo = st.file_uploader("Company Logo", type=["png", "jpg", "jpeg"], key="pdf_logo")

        # Store logo temporarily
        logo_path = ""
        if pdf_logo is not None:
            try:
                logo_bytes = pdf_logo.read()
                import tempfile
                logo_path = os.path.join(tempfile.gettempdir(), f"pv_logo_{pdf_logo.name}")
                with open(logo_path, "wb") as f:
                    f.write(logo_bytes)
            except Exception:
                logo_path = ""

        if not PDF_AVAILABLE:
            st.warning("PDF module not available. Install: uv add fpdf2 pillow")

    # Main content
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("🌞 Solar Resource Analysis")
        
        # Calculate solar position
        solar = calculate_solar_position(latitude, longitude, timezone, datetime(2024, 6, 21))
        
        # Display solar info
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Max Sun Elevation", f"{solar['max_elevation']:.1f}°")
        c2.metric("Min Sun Elevation", f"{solar['min_elevation']:.1f}°")
        c3.metric("Optimal Tilt", f"{tilt:.1f}°")
        c4.metric("Array Azimuth", f"{azimuth:.0f}°")
        
        # Sun path chart
        st.markdown("### Sun Path (Summer Solstice)")
        times = pd.date_range('2024-06-21', periods=24, freq='h', tz=timezone)
        loc = location.Location(latitude, longitude, tz=timezone)
        solpos = loc.get_solarposition(times)
        
        sun_path_data = pd.DataFrame({
            'Hour': times.hour,
            'Elevation': solpos['elevation'],
            'Azimuth': solpos['azimuth']
        })
        
        st.line_chart(
            sun_path_data.set_index('Hour')['Elevation'],
            use_container_width=True
        )
    
    with col2:
        st.subheader("📊 Quick Metrics")
        
        # Run simulation
        with st.spinner("Running simulation..."):
            if weather_source == "Open-Meteo (real)":
                weather, weather_origin = fetch_weather_or_fallback(
                    specs["latitude"], specs["longitude"],
                    specs.get("timezone", "Asia/Jakarta"),
                    int(weather_year),
                    fallback=lambda: generate_synthetic_weather(specs),
                )
            else:
                weather = generate_synthetic_weather(specs)
                weather_origin = "synthetic"
            results = simulate_pv_system(specs, weather)
        st.caption(f"Weather source: {weather_origin}")
        
        st.metric("Annual Production", f"{results['annual_kwh']:,.0f} kWh")
        st.metric("Specific Yield", f"{results['specific_yield']:,.0f} kWh/kWp")
        st.metric("Performance Ratio", f"{results['performance_ratio']:.1f}%")
        st.metric("Capacity Factor", f"{results['capacity_factor']:.1f}%")
    
    # Monthly production chart
    st.markdown("### 📈 Monthly Energy Production")
    monthly_df = pd.DataFrame({
        'Month': list(results['monthly_kwh'].keys()),
        'Energy (kWh)': list(results['monthly_kwh'].values())
    })
    st.bar_chart(monthly_df.set_index('Month'), use_container_width=True)
    
    # Financial metrics
    st.markdown("### 💰 Financial Analysis")
    f1, f2, f3, f4 = st.columns(4)
    f1.metric("System Cost", f"${results['system_cost']:,.0f}")
    f2.metric("Annual Savings", f"${results['annual_savings']:,.0f}/yr")
    f3.metric("Payback Period", f"{results['payback_years']:.1f} years")
    f4.metric("LCOE", f"${results['lcoe']:.3f}/kWh")

    # ====== STORAGE & SELF-CONSUMPTION SECTION ======
    stor = None  # Storage results dict for PDF report
    if enable_storage and STORAGE_AVAILABLE:
        st.markdown("---")
        st.subheader("🔋 Self-Consumption Optimizer (PLN Net Metering)")

        with st.spinner("Simulating battery & load flows..."):
            try:
                coordinator = StorageCoordinator()
                stor = coordinator.run_storage_simulation(
                    hourly_solar_kw=results['hourly_output'],
                    profile_type=sc_profile,
                    annual_load_kwh=sc_annual_load,
                    battery_capacity_kwh=batt_capacity,
                    battery_charge_kw=batt_charge,
                    battery_discharge_kw=batt_discharge,
                    tariff_code=sc_tariff,
                )

                # Top summary metrics
                s1, s2, s3, s4 = st.columns(4)
                s1.metric("Self-Consumption Ratio", f"{stor['self_consumption_ratio']*100:.1f}%")
                s2.metric("Self-Sufficiency", f"{stor['self_sufficiency_ratio']*100:.1f}%")
                s3.metric("Annual Savings", f"Rp {stor['annual_savings_idr']:,.0f}")
                s4.metric("Battery Payback", f"{stor['payback_years']:.1f} yrs")

                st.markdown("#### Energy Flow Summary (Annual)")
                fl1, fl2, fl3, fl4, fl5 = st.columns(5)
                fl1.metric("Solar Gen", f"{stor['total_solar_kwh']:,.0f} kWh")
                fl2.metric("Load Used", f"{stor['total_load_kwh']:,.0f} kWh")
                fl3.metric("Battery In", f"{stor['total_battery_charge_kwh']:,.0f} kWh")
                fl4.metric("Battery Out", f"{stor['total_battery_discharge_kwh']:,.0f} kWh")
                fl5.metric("Grid Import", f"{stor['total_grid_import_kwh']:,.0f} kWh")
                fl6, fl7, fl8 = st.columns(3)
                fl6.metric("Grid Export", f"{stor['total_grid_export_kwh']:,.0f} kWh")
                fl7.metric("Bill w/o PV", f"Rp {stor['total_bill_without_pv_idr']:,.0f}")
                fl8.metric("Bill w/ PV", f"Rp {stor['total_bill_with_pv_idr']:,.0f}")

                # Soc heatmap
                st.markdown("#### Battery State of Charge Heatmap")
                flows = stor['hourly_flows']
                # Reshape SOC to 24h x days for heatmap
                soc = flows['battery_soc'].values[:8760]
                hours = len(soc)
                days = hours // 24
                soc_matrix = soc[:days*24].reshape(days, 24)
                soc_df = pd.DataFrame(soc_matrix.T, columns=[f"Day {i+1}" for i in range(days)])
                # Downsample columns for display speed
                if len(soc_df.columns) > 100:
                    step = len(soc_df.columns) // 100
                    soc_df = soc_df.iloc[:, ::step]
                st.line_chart(soc_df.mean(axis=1), use_container_width=True)

                # Monthly bar chart: solar vs load vs import vs export
                st.markdown("#### Monthly Energy Flows")
                flows_monthly = flows.resample('ME', label='right').sum()[['solar_generation', 'load_consumption', 'grid_import', 'grid_export', 'battery_charge', 'battery_discharge']]
                st.bar_chart(flows_monthly, use_container_width=True)

                # Daily Sankey-style stacked area for a sample week
                st.markdown("#### Typical Week Energy Flow (Stacked)")
                week_flow = flows.head(168)[['solar_generation', 'load_consumption', 'grid_import', 'grid_export', 'battery_charge', 'battery_discharge']]
                st.area_chart(week_flow, use_container_width=True)

                # Agent insights
                with st.expander("🤖 Battery Agent Analysis"):
                    st.markdown("**Recommendation**")
                    st.info(stor['agent_recommendation'].get('insight', 'N/A'))
                    st.markdown("**Annual Analysis**")
                    st.info(stor['agent_analysis'])

            except Exception as e:
                st.error(f"Storage simulation failed: {e}")
                import traceback
                st.code(traceback.format_exc())
                stor = None

    # Reports section
    st.markdown("---")
    st.markdown("### 📄 Reports")
    
    # Generate report text
    report = generate_report(specs, results, solar)
    
    # PDF Report buttons
    if PDF_AVAILABLE:
        col_pdf1, col_pdf2, col_txt = st.columns(3)
        
        with col_pdf1:
            if st.button("📊 Generate PV Report PDF", use_container_width=True, type="secondary"):
                with st.spinner("Generating professional PDF..."):
                    try:
                        pdf_path = generate_pv_report_pdf(
                            specs=specs,
                            results=results,
                            solar=solar,
                            storage_results=stor,
                            company_name=pdf_company,
                            author_name=pdf_author,
                            logo_path=logo_path,
                            output_path=f"/tmp/pv_report_{location_name.replace(' ', '_').lower()}.pdf"
                        )
                        with open(pdf_path, "rb") as f:
                            st.download_button(
                                label="⬇️ Download PV Report PDF",
                                data=f,
                                file_name=f"pv_report_{location_name.replace(' ', '_').lower()}.pdf",
                                mime="application/pdf",
                                use_container_width=True
                            )
                    except Exception as e:
                        st.error(f"PDF generation failed: {e}")
        
        with col_pdf2:
            if st.session_state.get('ai_response') and st.button("🤖 Generate AI Analysis PDF", use_container_width=True, type="secondary"):
                with st.spinner("Generating AI analysis PDF..."):
                    try:
                        ai_pdf_path = generate_ai_analysis_pdf(
                            ai_response=st.session_state.ai_response,
                            chat_history=st.session_state.get('ai_chat_history', []),
                            specs=specs,
                            results=results,
                            company_name=pdf_company,
                            author_name=pdf_author,
                            logo_path=logo_path,
                            output_path=f"/tmp/pv_ai_analysis_{location_name.replace(' ', '_').lower()}.pdf"
                        )
                        with open(ai_pdf_path, "rb") as f:
                            st.download_button(
                                label="⬇️ Download AI Analysis PDF",
                                data=f,
                                file_name=f"pv_ai_analysis_{location_name.replace(' ', '_').lower()}.pdf",
                                mime="application/pdf",
                                use_container_width=True
                            )
                    except Exception as e:
                        st.error(f"AI PDF generation failed: {e}")
        
        with col_txt:
            st.download_button(
                label="📝 Download Text Report",
                data=report,
                file_name=f"pv_report_{location_name.replace(' ', '_').lower()}.txt",
                mime="text/plain",
                use_container_width=True
            )
    else:
        # Fallback when PDF not available
        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                label="📝 Download Text Report",
                data=report,
                file_name=f"pv_report_{location_name.replace(' ', '_').lower()}.txt",
                mime="text/plain",
                use_container_width=True
            )
        with col2:
            st.info("Install fpdf2 for PDF reports: uv add fpdf2 pillow")
    
    # AI Insights Panel
    if enable_ai and LLM_AVAILABLE:
        st.markdown("---")
        st.subheader("🤖 AI PV Advisor")

        # Session state for AI chat persistence
        if 'ai_response' not in st.session_state:
            st.session_state.ai_response = None
        if 'ai_chat_history' not in st.session_state:
            st.session_state.ai_chat_history = []

        # Generate button
        if ai_clicked and not st.session_state.ai_response:
            with st.spinner("Consulting AI agents..."):
                try:
                    llm = create_llm_provider(ai_provider, ai_model, ai_api_key)
                    if llm:
                        context = generate_pv_context(specs, results)
                        messages = [
                            {"role": "system", "content": "You are a senior solar PV engineer named Sunnyside. Analyze PV simulation results and provide actionable recommendations with clear bullet points."},
                            {"role": "user", "content": (
                                "Analyze the following PV simulation data and provide: "
                                "1) Key findings and system performance assessment, "
                                "2) Optimization suggestions (tilt, azimuth, DC/AC ratio, or module selection), "
                                "3) Financial feasibility summary, "
                                "4) Any risks or warnings.\n\n"
                                f"{context}"
                            )}
                        ]
                        st.session_state.ai_response = llm.chat(messages, temperature=0.3)
                        st.session_state.ai_chat_history.append({"role": "assistant", "content": st.session_state.ai_response})
                    else:
                        st.error("Failed to initialize LLM provider.")
                except Exception as e:
                    st.error(f"AI request failed: {e}")

        if ai_clicked and st.session_state.ai_response:
            st.success("Sunnyside analysis complete")
            st.markdown(f"""
            <div style="background-color:#1e1e2f; color:#e0e0e0; padding:1.2rem; border-radius:0.5rem; line-height:1.6;">
                {st.session_state.ai_response.replace(chr(10), '<br>')}
            </div>
            """, unsafe_allow_html=True)

            # Chat input follow-up
            user_question = st.chat_input("Ask follow-up question...")
            if user_question:
                with st.spinner("Thinking..."):
                    try:
                        llm = create_llm_provider(ai_provider, ai_model, ai_api_key)
                        follow_messages = [
                            {"role": "system", "content": "You are Sunnyside, a senior PV engineer. Use the previous simulation context to answer the user's follow-up question."},
                            {"role": "user", "content": generate_pv_context(specs, results)},
                            {"role": "assistant", "content": st.session_state.ai_response},
                            {"role": "user", "content": user_question}
                        ]
                        answer = llm.chat(follow_messages, temperature=0.3)
                        st.session_state.ai_chat_history.append({"role": "user", "content": user_question})
                        st.session_state.ai_chat_history.append({"role": "assistant", "content": answer})
                    except Exception as e:
                        st.error(f"Follow-up failed: {e}")

            # Display chat history
            if len(st.session_state.ai_chat_history) > 0:
                st.markdown("**Chat History**")
                for msg in st.session_state.ai_chat_history:
                    role_icon = "👤" if msg["role"] == "user" else "🤖"
                    st.markdown(f"{role_icon} **{msg['role'].title()}:** {msg['content']}")

            # Clear button
            if st.button("🔄 Reset AI Chat", use_container_width=True):
                st.session_state.ai_response = None
                st.session_state.ai_chat_history = []
                st.rerun()

        elif enable_ai and not st.session_state.ai_response:
            st.info("Click '🚀 Generate AI Insights' in the sidebar to get AI-powered analysis.")

    # Hourly output chart
    st.markdown("### ⚡ Hourly Output Sample (First Week)")
    hourly_sample = results['hourly_output'].iloc[:168]  # First week
    hourly_df = pd.DataFrame({
        'DateTime': hourly_sample.index,
        'AC Power (kW)': hourly_sample.values
    }).set_index('DateTime')
    st.line_chart(hourly_df, use_container_width=True)
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style='text-align: center; color: #666;'>
        <b>Sunnyside AI | PV Simulator</b> | 
        Powered by PVlib + Multi-Agent AI | 
        <a href='https://github.com/zakusworo/pv-multi-agent'>View on GitHub</a>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
