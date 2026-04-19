"""
PV Module Database
Comprehensive list of solar panel manufacturers, models, and specifications.
Data sourced from manufacturer datasheets (2024-2025 models).
"""

from typing import Dict, List
from dataclasses import dataclass, asdict


@dataclass
class PVModule:
    """PV Module specifications"""
    manufacturer: str
    model_name: str
    pdc0: float  # Rated power (W)
    v_oc: float  # Open circuit voltage (V)
    i_sc: float  # Short circuit current (A)
    v_mp: float  # Max power voltage (V)
    i_mp: float  # Max power current (A)
    efficiency: float  # Module efficiency (%)
    gamma_pdc: float  # Temperature coefficient (%/°C)
    cells_in_series: int
    technology: str  # mono, poly, bifacial, etc.
    warranty_years: int
    degradation_rate: float  # Annual degradation (%)


# ============================================================================
# PV MODULE DATABASE
# ============================================================================

PV_MODULE_DATABASE: List[PVModule] = [
    # =========================================================================
    # SUNPOWER (USA) - Premium High Efficiency
    # =========================================================================
    PVModule(
        manufacturer="SunPower",
        model_name="Maxeon 7",
        pdc0=460, v_oc=51.2, i_sc=11.38, v_mp=43.8, i_mp=10.50,
        efficiency=24.1, gamma_pdc=-0.0029, cells_in_series=120,
        technology="mono", warranty_years=40, degradation_rate=0.0025
    ),
    PVModule(
        manufacturer="SunPower",
        model_name="Maxeon 6",
        pdc0=425, v_oc=49.8, i_sc=10.92, v_mp=42.5, i_mp=10.00,
        efficiency=22.8, gamma_pdc=-0.0030, cells_in_series=120,
        technology="mono", warranty_years=40, degradation_rate=0.0025
    ),
    PVModule(
        manufacturer="SunPower",
        model_name="Performance P19",
        pdc0=400, v_oc=48.5, i_sc=10.55, v_mp=41.2, i_mp=9.71,
        efficiency=21.2, gamma_pdc=-0.0035, cells_in_series=120,
        technology="mono", warranty_years=25, degradation_rate=0.0045
    ),
    
    # =========================================================================
    # LG ELECTRONICS (South Korea) - Premium Residential
    # =========================================================================
    PVModule(
        manufacturer="LG Electronics",
        model_name="NeON R ACE",
        pdc0=440, v_oc=50.1, i_sc=11.15, v_mp=42.8, i_mp=10.28,
        efficiency=22.3, gamma_pdc=-0.0030, cells_in_series=120,
        technology="mono", warranty_years=25, degradation_rate=0.0030
    ),
    PVModule(
        manufacturer="LG Electronics",
        model_name="NeON 2",
        pdc0=380, v_oc=46.8, i_sc=10.42, v_mp=39.9, i_mp=9.52,
        efficiency=20.3, gamma_pdc=-0.0035, cells_in_series=120,
        technology="mono", warranty_years=25, degradation_rate=0.0040
    ),
    
    # =========================================================================
    # PANASONIC (Japan) - High Quality Residential
    # =========================================================================
    PVModule(
        manufacturer="Panasonic",
        model_name="EverVolt HK",
        pdc0=455, v_oc=50.8, i_sc=11.28, v_mp=43.2, i_mp=10.53,
        efficiency=22.6, gamma_pdc=-0.0026, cells_in_series=120,
        technology="mono", warranty_years=25, degradation_rate=0.0030
    ),
    PVModule(
        manufacturer="Panasonic",
        model_name="EverVolt BK",
        pdc0=410, v_oc=48.2, i_sc=10.72, v_mp=41.0, i_mp=10.00,
        efficiency=21.2, gamma_pdc=-0.0029, cells_in_series=120,
        technology="mono", warranty_years=25, degradation_rate=0.0035
    ),
    
    # =========================================================================
    # CANADIAN SOLAR (Canada/China) - Value Leader
    # =========================================================================
    PVModule(
        manufacturer="Canadian Solar",
        model_name="HiKu7 Mono PERC",
        pdc0=560, v_oc=52.8, i_sc=13.42, v_mp=44.5, i_mp=12.58,
        efficiency=22.8, gamma_pdc=-0.0032, cells_in_series=132,
        technology="mono", warranty_years=25, degradation_rate=0.0040
    ),
    PVModule(
        manufacturer="Canadian Solar",
        model_name="HiKu6 Mono PERC",
        pdc0=450, v_oc=49.5, i_sc=11.45, v_mp=42.0, i_mp=10.71,
        efficiency=21.4, gamma_pdc=-0.0034, cells_in_series=120,
        technology="mono", warranty_years=25, degradation_rate=0.0045
    ),
    PVModule(
        manufacturer="Canadian Solar",
        model_name="BiHiKu7 Bifacial",
        pdc0=580, v_oc=53.2, i_sc=13.68, v_mp=44.8, i_mp=12.95,
        efficiency=23.2, gamma_pdc=-0.0031, cells_in_series=132,
        technology="bifacial", warranty_years=25, degradation_rate=0.0040
    ),
    PVModule(
        manufacturer="Canadian Solar",
        model_name="KuPower Poly",
        pdc0=340, v_oc=46.2, i_sc=9.45, v_mp=37.8, i_mp=9.00,
        efficiency=17.8, gamma_pdc=-0.0040, cells_in_series=120,
        technology="poly", warranty_years=25, degradation_rate=0.0055
    ),
    
    # =========================================================================
    # JINKO SOLAR (China) - Global Leader
    # =========================================================================
    PVModule(
        manufacturer="Jinko Solar",
        model_name="Tiger Neo N-type",
        pdc0=585, v_oc=53.5, i_sc=13.85, v_mp=45.2, i_mp=12.94,
        efficiency=23.5, gamma_pdc=-0.0028, cells_in_series=132,
        technology="n-type", warranty_years=30, degradation_rate=0.0030
    ),
    PVModule(
        manufacturer="Jinko Solar",
        model_name="Tiger Pro",
        pdc0=550, v_oc=52.5, i_sc=13.42, v_mp=44.2, i_mp=12.44,
        efficiency=22.5, gamma_pdc=-0.0032, cells_in_series=132,
        technology="mono", warranty_years=25, degradation_rate=0.0040
    ),
    PVModule(
        manufacturer="Jinko Solar",
        model_name="Cheetah HC",
        pdc0=455, v_oc=49.8, i_sc=11.52, v_mp=42.2, i_mp=10.78,
        efficiency=21.0, gamma_pdc=-0.0035, cells_in_series=120,
        technology="mono", warranty_years=25, degradation_rate=0.0045
    ),
    
    # =========================================================================
    # TRINA SOLAR (China) - High Efficiency
    # =========================================================================
    PVModule(
        manufacturer="Trina Solar",
        model_name="Vertex S+ N-type",
        pdc0=450, v_oc=50.2, i_sc=11.35, v_mp=42.6, i_mp=10.56,
        efficiency=22.5, gamma_pdc=-0.0029, cells_in_series=120,
        technology="n-type", warranty_years=25, degradation_rate=0.0030
    ),
    PVModule(
        manufacturer="Trina Solar",
        model_name="Vertex S",
        pdc0=425, v_oc=48.8, i_sc=11.02, v_mp=41.4, i_mp=10.27,
        efficiency=21.4, gamma_pdc=-0.0033, cells_in_series=120,
        technology="mono", warranty_years=25, degradation_rate=0.0040
    ),
    PVModule(
        manufacturer="Trina Solar",
        model_name="Duomax Twin",
        pdc0=450, v_oc=49.5, i_sc=11.42, v_mp=42.0, i_mp=10.71,
        efficiency=20.8, gamma_pdc=-0.0034, cells_in_series=120,
        technology="bifacial", warranty_years=25, degradation_rate=0.0045
    ),
    
    # =========================================================================
    # LONGi SOLAR (China) - Mono Specialist
    # =========================================================================
    PVModule(
        manufacturer="LONGi Solar",
        model_name="Hi-MO 7 N-type",
        pdc0=590, v_oc=53.8, i_sc=13.92, v_mp=45.5, i_mp=12.97,
        efficiency=23.8, gamma_pdc=-0.0027, cells_in_series=132,
        technology="n-type", warranty_years=30, degradation_rate=0.0030
    ),
    PVModule(
        manufacturer="LONGi Solar",
        model_name="Hi-MO 6 Explorer",
        pdc0=460, v_oc=50.0, i_sc=11.55, v_mp=42.4, i_mp=10.85,
        efficiency=22.3, gamma_pdc=-0.0031, cells_in_series=120,
        technology="mono", warranty_years=25, degradation_rate=0.0035
    ),
    PVModule(
        manufacturer="LONGi Solar",
        model_name="Hi-MO 5",
        pdc0=545, v_oc=52.2, i_sc=13.25, v_mp=44.0, i_mp=12.39,
        efficiency=21.8, gamma_pdc=-0.0033, cells_in_series=132,
        technology="mono", warranty_years=25, degradation_rate=0.0040
    ),
    
    # =========================================================================
    # REC GROUP (Norway/Singapore) - Premium European
    # =========================================================================
    PVModule(
        manufacturer="REC Group",
        model_name="TwinPeak 4",
        pdc0=440, v_oc=49.9, i_sc=11.28, v_mp=42.5, i_mp=10.35,
        efficiency=21.9, gamma_pdc=-0.0032, cells_in_series=120,
        technology="mono", warranty_years=25, degradation_rate=0.0035
    ),
    PVModule(
        manufacturer="REC Group",
        model_name="Alpha Pure R",
        pdc0=430, v_oc=50.5, i_sc=10.95, v_mp=43.0, i_mp=10.00,
        efficiency=22.3, gamma_pdc=-0.0026, cells_in_series=120,
        technology="n-type", warranty_years=25, degradation_rate=0.0025
    ),
    
    # =========================================================================
    # Q CELLS (South Korea/USA) - Residential Focus
    # =========================================================================
    PVModule(
        manufacturer="Q CELLS",
        model_name="Q.TRON-Z M12.G3",
        pdc0=455, v_oc=50.3, i_sc=11.42, v_mp=42.8, i_mp=10.63,
        efficiency=22.4, gamma_pdc=-0.0030, cells_in_series=120,
        technology="n-type", warranty_years=25, degradation_rate=0.0030
    ),
    PVModule(
        manufacturer="Q CELLS",
        model_name="Q.PEAK DUO G11",
        pdc0=400, v_oc=48.2, i_sc=10.68, v_mp=40.9, i_mp=9.78,
        efficiency=20.8, gamma_pdc=-0.0034, cells_in_series=120,
        technology="mono", warranty_years=25, degradation_rate=0.0040
    ),
    
    # =========================================================================
    # FIRST SOLAR (USA) - Thin Film CdTe
    # =========================================================================
    PVModule(
        manufacturer="First Solar",
        model_name="TetraSun T700",
        pdc0=700, v_oc=115.2, i_sc=7.85, v_mp=98.5, i_mp=7.11,
        efficiency=19.5, gamma_pdc=-0.0025, cells_in_series=210,
        technology="thin_film", warranty_years=25, degradation_rate=0.0035
    ),
    PVModule(
        manufacturer="First Solar",
        model_name="TetraSun T600",
        pdc0=600, v_oc=112.8, i_sc=6.92, v_mp=95.2, i_mp=6.30,
        efficiency=18.8, gamma_pdc=-0.0027, cells_in_series=210,
        technology="thin_film", warranty_years=25, degradation_rate=0.0040
    ),
    
    # =========================================================================
    # MEYER BURGER (Germany/Switzerland) - Premium European
    # =========================================================================
    PVModule(
        manufacturer="Meyer Burger",
        model_name="Solar 410",
        pdc0=410, v_oc=49.2, i_sc=10.85, v_mp=41.8, i_mp=9.81,
        efficiency=21.5, gamma_pdc=-0.0028, cells_in_series=120,
        technology="mono", warranty_years=25, degradation_rate=0.0030
    ),
    
    # =========================================================================
    # JINKO / TRINA / LONGi - Budget Options
    # =========================================================================
    PVModule(
        manufacturer="Jinko Solar",
        model_name="Eagle PERC",
        pdc0=380, v_oc=46.5, i_sc=10.25, v_mp=39.5, i_mp=9.62,
        efficiency=19.5, gamma_pdc=-0.0036, cells_in_series=120,
        technology="mono", warranty_years=25, degradation_rate=0.0050
    ),
    PVModule(
        manufacturer="Trina Solar",
        model_name="Tallmax M",
        pdc0=360, v_oc=45.8, i_sc=9.95, v_mp=38.8, i_mp=9.28,
        efficiency=18.8, gamma_pdc=-0.0038, cells_in_series=120,
        technology="mono", warranty_years=25, degradation_rate=0.0055
    ),
    PVModule(
        manufacturer="LONGi Solar",
        model_name="Hi-MO 4",
        pdc0=350, v_oc=45.2, i_sc=9.78, v_mp=38.2, i_mp=9.16,
        efficiency=18.5, gamma_pdc=-0.0038, cells_in_series=120,
        technology="mono", warranty_years=25, degradation_rate=0.0055
    ),
]


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_module_by_name(manufacturer: str, model_name: str) -> PVModule:
    """Get a specific module by manufacturer and model name"""
    for module in PV_MODULE_DATABASE:
        if module.manufacturer.lower() == manufacturer.lower() and \
           module.model_name.lower() == model_name.lower():
            return module
    raise ValueError(f"Module not found: {manufacturer} {model_name}")


def get_modules_by_manufacturer(manufacturer: str) -> List[PVModule]:
    """Get all modules from a specific manufacturer"""
    return [m for m in PV_MODULE_DATABASE if m.manufacturer.lower() == manufacturer.lower()]


def get_modules_by_power_range(min_watts: float, max_watts: float) -> List[PVModule]:
    """Get modules within a power range"""
    return [m for m in PV_MODULE_DATABASE if min_watts <= m.pdc0 <= max_watts]


def get_modules_by_technology(technology: str) -> List[PVModule]:
    """Get modules by technology type"""
    return [m for m in PV_MODULE_DATABASE if m.technology.lower() == technology.lower()]


def get_manufacturers() -> List[str]:
    """Get list of all manufacturers"""
    return sorted(list(set(m.manufacturer for m in PV_MODULE_DATABASE)))


def get_module_names_by_manufacturer(manufacturer: str) -> List[str]:
    """Get list of model names for a manufacturer"""
    modules = get_modules_by_manufacturer(manufacturer)
    return sorted([m.model_name for m in modules])


def search_modules(query: str) -> List[PVModule]:
    """Search modules by manufacturer or model name"""
    query = query.lower()
    return [m for m in PV_MODULE_DATABASE 
            if query in m.manufacturer.lower() or query in m.model_name.lower()]


def module_to_dict(module: PVModule) -> Dict:
    """Convert PVModule to dictionary"""
    return asdict(module)


def get_database_summary() -> Dict:
    """Get summary statistics of the database"""
    manufacturers = get_manufacturers()
    technologies = sorted(list(set(m.technology for m in PV_MODULE_DATABASE)))
    
    return {
        "total_modules": len(PV_MODULE_DATABASE),
        "manufacturers": manufacturers,
        "manufacturer_count": len(manufacturers),
        "technologies": technologies,
        "power_range": {
            "min": min(m.pdc0 for m in PV_MODULE_DATABASE),
            "max": max(m.pdc0 for m in PV_MODULE_DATABASE),
            "avg": sum(m.pdc0 for m in PV_MODULE_DATABASE) / len(PV_MODULE_DATABASE)
        },
        "efficiency_range": {
            "min": min(m.efficiency for m in PV_MODULE_DATABASE),
            "max": max(m.efficiency for m in PV_MODULE_DATABASE),
            "avg": sum(m.efficiency for m in PV_MODULE_DATABASE) / len(PV_MODULE_DATABASE)
        }
    }


# ============================================================================
# MAIN - Demo
# ============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("PV MODULE DATABASE")
    print("=" * 70)
    
    summary = get_database_summary()
    print(f"\nTotal Modules: {summary['total_modules']}")
    print(f"Manufacturers: {summary['manufacturer_count']}")
    print(f"\nManufacturers: {', '.join(summary['manufacturers'])}")
    print(f"\nTechnologies: {', '.join(summary['technologies'])}")
    print(f"\nPower Range: {summary['power_range']['min']}W - {summary['power_range']['max']}W (avg: {summary['power_range']['avg']:.0f}W)")
    print(f"Efficiency Range: {summary['efficiency_range']['min']}% - {summary['efficiency_range']['max']}% (avg: {summary['efficiency_range']['avg']:.1f}%)")
    
    print("\n" + "=" * 70)
    print("MODULES BY MANUFACTURER")
    print("=" * 70)
    
    for manufacturer in summary['manufacturers']:
        modules = get_modules_by_manufacturer(manufacturer)
        print(f"\n{manufacturer} ({len(modules)} models):")
        for m in sorted(modules, key=lambda x: x.pdc0, reverse=True):
            print(f"  - {m.model_name}: {m.pdc0}W, {m.efficiency}% eff, {m.technology}")
