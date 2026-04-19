#!/usr/bin/env python3
"""
Streamlit GUI for Multi-Agent PV System Calculator
Run with: streamlit run gui.py
"""

import streamlit as st
import pandas as pd
import numpy as np
import pvlib
from pvlib import location, irradiance
from datetime import datetime, timedelta
from typing import Dict, Any
import json
import os

# Page config
st.set_page_config(
    page_title="PV Multi-Agent Calculator",
    page_icon="☀️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 1rem;
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


def simulate_pv_system(specs: Dict, weather: pd.DataFrame) -> Dict:
    """Run PV system simulation"""
    latitude = specs['latitude']
    longitude = specs['longitude']
    altitude = specs.get('altitude', 0)
    timezone = specs.get('timezone', 'Asia/Jakarta')
    tilt = specs.get('tilt', abs(latitude))
    azimuth = specs.get('azimuth', 0)
    system_capacity_kw = specs.get('system_capacity_kw', 10.0)
    module_type = specs.get('module_type', 'standard_mono')
    
    # Create location
    loc = location.Location(latitude, longitude, altitude=altitude, tz=timezone)
    
    # Solar position
    solar_pos = loc.get_solarposition(weather.index)
    
    # Extra terrestrial irradiance
    dni_extra = irradiance.get_extra_radiation(weather.index)
    
    # POA irradiance
    poa_global = irradiance.get_total_irradiance(
        tilt, azimuth,
        solar_pos['zenith'], solar_pos['azimuth'],
        weather['dni'].fillna(0),
        weather['ghi'].fillna(0),
        weather['dhi'].fillna(0),
        dni_extra=dni_extra,
        model='haydavies'
    )['poa_global']
    
    # Module parameters
    module_params = {
        'standard_poly': {'pdc0': 330, 'gamma_pdc': -0.004},
        'standard_mono': {'pdc0': 450, 'gamma_pdc': -0.0035},
        'premium_mono': {'pdc0': 545, 'gamma_pdc': -0.003}
    }.get(module_type, {'pdc0': 450, 'gamma_pdc': -0.0035})
    
    # Calculate modules needed
    num_modules = int(np.ceil(system_capacity_kw * 1000 / module_params['pdc0']))
    actual_capacity_kw = num_modules * module_params['pdc0'] / 1000
    
    # Cell temperature
    temp_cell = weather['temp_air'] + poa_global * 0.02
    
    # DC power
    gamma = module_params['gamma_pdc']
    dc_power = actual_capacity_kw * (poa_global / 1000) * (1 + gamma * (temp_cell - 25))
    dc_power = dc_power.clip(lower=0)
    
    # AC power (simple inverter model)
    inverter_efficiency = specs.get('inverter_efficiency', 0.96)
    ac_capacity_kw = specs.get('ac_capacity_kw', actual_capacity_kw * 0.9)
    ac_power = (dc_power * inverter_efficiency).clip(upper=ac_capacity_kw)
    
    # Results
    hourly_ac = ac_power.fillna(0)
    annual_kwh = hourly_ac.sum()
    
    # Monthly breakdown
    monthly = {}
    month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                   'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    for i, month_name in enumerate(month_names, 1):
        monthly[month_name] = hourly_ac[hourly_ac.index.month == i].sum()
    
    # Performance metrics
    specific_yield = annual_kwh / actual_capacity_kw if actual_capacity_kw > 0 else 0
    capacity_factor = annual_kwh / (actual_capacity_kw * 8760) * 100 if actual_capacity_kw > 0 else 0
    performance_ratio = min(85, max(70, capacity_factor * 1.2))
    
    # Financial
    cost_per_watt = specs.get('cost_per_watt', 2.50)
    electricity_rate = specs.get('electricity_rate', 0.13)
    system_cost = actual_capacity_kw * 1000 * cost_per_watt
    annual_savings = annual_kwh * electricity_rate
    payback = system_cost / annual_savings if annual_savings > 0 else float('inf')
    lcoe = system_cost / (annual_kwh * 25) if annual_kwh > 0 else float('inf')
    
    return {
        'annual_kwh': annual_kwh,
        'specific_yield': specific_yield,
        'capacity_factor': capacity_factor,
        'performance_ratio': performance_ratio,
        'monthly_kwh': monthly,
        'peak_power_kw': hourly_ac.max(),
        'dc_capacity_kw': actual_capacity_kw,
        'ac_capacity_kw': ac_capacity_kw,
        'num_modules': num_modules,
        'system_cost': system_cost,
        'annual_savings': annual_savings,
        'payback_years': payback,
        'lcoe': lcoe,
        'hourly_output': hourly_ac
    }


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


# ============== Main App ==============

def main():
    # Header
    st.markdown('<p class="main-header">☀️ Multi-Agent PV System Calculator</p>', unsafe_allow_html=True)
    st.markdown("""
    <div style='text-align: center; color: #666; margin-bottom: 2rem;'>
        AI-powered solar energy simulation with physics-based pvlib engine
    </div>
    """, unsafe_allow_html=True)
    
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
        
        st.header("⚙️ System Design")
        
        system_capacity = st.slider("System Capacity (kW)", 1.0, 100.0, 10.0, 0.5)
        module_type = st.selectbox(
            "Module Type",
            ["standard_mono", "standard_poly", "premium_mono"],
            format_func=lambda x: x.replace('_', ' ').title()
        )
        
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
        
        # Store specs
        specs = {
            'name': location_name,
            'latitude': latitude,
            'longitude': longitude,
            'altitude': altitude,
            'timezone': timezone,
            'system_capacity_kw': system_capacity,
            'module_type': module_type,
            'tilt': tilt,
            'azimuth': azimuth,
            'inverter_efficiency': 0.96,
            'cost_per_watt': cost_per_watt,
            'electricity_rate': electricity_rate
        }
    
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
            weather = generate_synthetic_weather(specs)
            results = simulate_pv_system(specs, weather)
        
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
    
    # Full report
    with st.expander("📄 View Full Report"):
        report = generate_report(specs, results, solar)
        st.text(report)
        
        # Download button
        st.download_button(
            label="Download Report (.txt)",
            data=report,
            file_name=f"pv_report_{location_name.replace(' ', '_').lower()}.txt",
            mime="text/plain"
        )
    
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
        <b>Multi-Agent PV System Calculator</b> | 
        Powered by PVlib Python + Streamlit | 
        <a href='https://github.com/yourusername/pv-multi-agent'>View on GitHub</a>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
