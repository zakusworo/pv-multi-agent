#!/usr/bin/env python3
"""
PV Module Database Fetcher
Dynamically fetches updated PV module data from public sources.

Sources:
1. PVLib CEC Module Database (via pvlib Python library) - Primary
2. Open Solar Facts API - Secondary
3. Fallback to static database

Data is cached locally and can be refreshed on demand.
"""

import os
import json
import hashlib
from datetime import datetime, timedelta
import os
import sys
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _project_root)
sys.path.insert(0, os.path.join(_project_root, 'data'))

from typing import Dict, List, Optional
from pathlib import Path

# Cache configuration
CACHE_DIR = Path.home() / ".pv-multi-agent" / "module_cache"
CACHE_FILE = CACHE_DIR / "pv_modules.json"
CACHE_METADATA = CACHE_DIR / "metadata.json"
CACHE_EXPIRY_DAYS = 7  # Refresh cache weekly


def ensure_cache_dir():
    """Create cache directory if it doesn't exist"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def get_cache_hash() -> Optional[str]:
    """Get hash of current cache file"""
    if CACHE_FILE.exists():
        with open(CACHE_FILE, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()
    return None


def save_cache(modules: List[Dict], source: str):
    """Save modules to cache"""
    ensure_cache_dir()
    
    metadata = {
        "last_updated": datetime.now().isoformat(),
        "source": source,
        "module_count": len(modules),
        "cache_hash": get_cache_hash()
    }
    
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(modules, f, indent=2, default=str)
    
    with open(CACHE_METADATA, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2)
    
    print(f"✓ Cached {len(modules)} modules from {source}")


def load_cache() -> Optional[List[Dict]]:
    """Load modules from cache if not expired"""
    if not CACHE_FILE.exists():
        return None
    
    if not CACHE_METADATA.exists():
        return None
    
    try:
        with open(CACHE_METADATA, 'r') as f:
            metadata = json.load(f)
        
        last_updated = datetime.fromisoformat(metadata['last_updated'])
        age = datetime.now() - last_updated
        
        if age > timedelta(days=CACHE_EXPIRY_DAYS):
            print(f"⚠ Cache expired ({age.days} days old)")
            return None
        
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            modules = json.load(f)
        
        print(f"✓ Loaded {len(modules)} modules from cache ({age.days} days old)")
        return modules
    
    except Exception as e:
        print(f"⚠ Cache load error: {e}")
        return None


def fetch_from_pvlib() -> List[Dict]:
    """
    Fetch from PVLib's built-in CEC module database
    
    PVLib includes the California Energy Commission (CEC) module database
    which is updated regularly and contains thousands of commercially
    available modules.
    
    Returns list of module dictionaries
    """
    print("📡 Fetching from PVLib CEC module database...")
    
    try:
        import pvlib
        
        # Get CEC module database from pvlib
        cec_modules = pvlib.pvsystem.retrieve_sam('CECMod')
        
        print(f"  Found {len(cec_modules.columns)} total modules in database")
        
        modules = []
        
        for col in cec_modules.columns:
            try:
                data = cec_modules[col]
                
                # Parse manufacturer and model from column name
                # Format is typically "Manufacturer_Model"
                parts = col.split('_')
                manufacturer = parts[0] if parts else 'Unknown'
                model_name = '_'.join(parts[1:]) if len(parts) > 1 else col
                
                # Get electrical parameters (correct PVLib parameter names)
                v_mp = float(data.get('V_mp_ref', 0))
                i_mp = float(data.get('I_mp_ref', 0))
                v_oc = float(data.get('V_oc_ref', 0))
                i_sc = float(data.get('I_sc_ref', 0))
                
                # Calculate power from Vmp and Imp
                pdc0 = v_mp * i_mp if (v_mp > 0 and i_mp > 0) else 0
                
                # Skip if no valid power
                if pdc0 < 350:
                    continue
                
                # Get efficiency - calculate from power and area
                area = float(data.get('A_c', 0))  # Cell area in m²
                if area > 0:
                    efficiency = (pdc0 / 1000) / area * 100
                else:
                    # Skip if no area data
                    continue
                
                # Skip low efficiency modules
                if efficiency < 17:
                    continue
                
                # Get temperature coefficient (gamma_r is in %/C)
                gamma_pdc = float(data.get('gamma_r', -0.4)) / 100  # Convert to 1/C
                
                # Get number of cells
                n_s = int(data.get('N_s', 60))
                
                # Check if bifacial
                bifacial = bool(data.get('Bifacial', False))
                
                module = {
                    "manufacturer": manufacturer.replace('_', ' ').strip(),
                    "model_name": model_name.replace('_', ' ').strip(),
                    "pdc0": round(pdc0, 1),
                    "v_oc": round(v_oc, 2),
                    "i_sc": round(i_sc, 2),
                    "v_mp": round(v_mp, 2),
                    "i_mp": round(i_mp, 2),
                    "efficiency": round(efficiency, 2),
                    "gamma_pdc": round(gamma_pdc, 5),
                    "cells_in_series": n_s,
                    "technology": classify_technology_from_name(model_name, manufacturer, data.get('Technology', '')),
                    "warranty_years": 25,
                    "degradation_rate": 0.0045,
                    "source": "CEC via PVLib",
                    "bifacial": bifacial
                }
                
                modules.append(module)
            
            except Exception as e:
                continue
        
        print(f"  ✓ Fetched {len(modules)} modern production modules from PVLib CEC database")
        return modules
    
    except ImportError:
        print("  ⚠ PVLib not installed")
        return []
    except Exception as e:
        print(f"  ⚠ Failed to fetch from PVLib: {e}")
        return []


def classify_technology_from_name(model_name: str, manufacturer: str, technology_str: str = '') -> str:
    """Classify module technology based on name and technology string"""
    name_lower = model_name.lower() + ' ' + manufacturer.lower()
    tech_lower = technology_str.lower() if technology_str else ''
    
    # Check technology string first (from PVLib)
    if 'poly' in tech_lower or 'multi' in tech_lower:
        return 'poly'
    elif 'mono' in tech_lower:
        # Check if it's actually bifacial or n-type
        if 'bifacial' in name_lower or 'bifi' in name_lower:
            return 'bifacial'
        elif 'n-type' in name_lower or 'ntype' in name_lower or 'topcon' in name_lower:
            return 'n-type'
        else:
            return 'mono'
    elif 'thin' in tech_lower or 'cdte' in tech_lower or 'cis' in tech_lower:
        return 'thin_film'
    
    # Fall back to name-based classification
    if 'bifacial' in name_lower or 'bifi' in name_lower:
        return 'bifacial'
    elif 'n-type' in name_lower or 'ntype' in name_lower or 'topcon' in name_lower:
        return 'n-type'
    elif 'poly' in name_lower or 'multi' in name_lower:
        return 'poly'
    elif 'thin' in name_lower or 'cdte' in name_lower or 'cis' in name_lower or 'first solar' in name_lower:
        return 'thin_film'
    else:
        return 'mono'


def fetch_from_opensolar() -> List[Dict]:
    """
    Fetch from Open Solar Facts API
    
    This is a community-maintained database of solar equipment.
    API: https://api.opensolar.com/facts/v1/modules
    
    Returns list of module dictionaries
    """
    print("📡 Fetching from Open Solar Facts API...")
    
    try:
        import requests
        
        url = "https://api.opensolar.com/facts/v1/modules"
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        modules = []
        
        for item in data.get('modules', []):
            try:
                module = {
                    "manufacturer": item.get('manufacturer', ''),
                    "model_name": item.get('model', ''),
                    "pdc0": float(item.get('power', 0)),
                    "v_oc": float(item.get('voc', 0)),
                    "i_sc": float(item.get('isc', 0)),
                    "v_mp": float(item.get('vmp', 0)),
                    "i_mp": float(item.get('imp', 0)),
                    "efficiency": float(item.get('efficiency', 0)),
                    "gamma_pdc": float(item.get('temperature_coefficient', -0.4)) / 100,
                    "cells_in_series": int(item.get('cells', 60)),
                    "technology": item.get('technology', 'mono'),
                    "warranty_years": int(item.get('warranty', 25)),
                    "degradation_rate": 0.0045,
                    "source": "OpenSolar"
                }
                
                if module['pdc0'] > 0:
                    modules.append(module)
            
            except (ValueError, KeyError):
                continue
        
        print(f"  ✓ Fetched {len(modules)} modules from OpenSolar")
        return modules
    
    except Exception as e:
        print(f"  ⚠ Failed to fetch from OpenSolar: {e}")
        return []


def deduplicate_modules(modules: List[Dict]) -> List[Dict]:
    """Remove duplicate modules (same manufacturer + model)"""
    seen = set()
    unique = []
    
    for module in modules:
        key = f"{module['manufacturer']}_{module['model_name']}"
        if key not in seen:
            seen.add(key)
            unique.append(module)
    
    return unique


def filter_production_modules(modules: List[Dict], max_modules: int = 200) -> List[Dict]:
    """
    Filter to only modules likely still in production
    
    Criteria:
    - Power rating >= 350W (modern modules)
    - Efficiency >= 17% (reasonable efficiency)
    - From active manufacturers
    - Limit to top modules by power per manufacturer
    """
    active_manufacturers = [
        'longi', 'jinko', 'trina', 'canadian', 'sunpower', 'lg',
        'panasonic', 'q cells', 'rec', 'first solar', 'meyer burger',
        'hanwha', 'hyundai', 'axitec', 'phono', 'ja solar', 'risen',
        'suntech', 'yingli', 'gne', 'tw', 'maxeon'
    ]
    
    # Group by manufacturer
    by_manufacturer = {}
    for module in modules:
        manufacturer_lower = module['manufacturer'].lower()
        if not any(m in manufacturer_lower for m in active_manufacturers):
            continue
        
        if module['pdc0'] < 350 or module['efficiency'] < 17:
            continue
        
        if manufacturer_lower not in by_manufacturer:
            by_manufacturer[manufacturer_lower] = []
        by_manufacturer[manufacturer_lower].append(module)
    
    # Take top 10 modules by power from each manufacturer
    filtered = []
    for manufacturer, mods in by_manufacturer.items():
        mods.sort(key=lambda x: -x['pdc0'])
        filtered.extend(mods[:max_modules // len(by_manufacturer) + 1])
    
    return filtered


def fetch_all_modules(force_refresh: bool = False) -> List[Dict]:
    """
    Fetch modules from all sources, with caching
    
    Args:
        force_refresh: If True, ignore cache and fetch fresh data
    
    Returns:
        List of module dictionaries
    """
    # Try to load from cache first
    if not force_refresh:
        cached = load_cache()
        if cached:
            return cached
    
    print("\n🔄 Fetching updated PV module database...\n")
    
    all_modules = []
    
    # Try sources in order of preference
    sources = [
        ("PVLib CEC", fetch_from_pvlib),
        ("OpenSolar", fetch_from_opensolar)
    ]
    
    for source_name, fetch_func in sources:
        try:
            modules = fetch_func()
            if modules:
                all_modules.extend(modules)
                print(f"✓ {source_name}: {len(modules)} modules\n")
                break  # Use first successful source
        except Exception as e:
            print(f"✗ {source_name} failed: {e}\n")
            continue
    
    if not all_modules:
        print("⚠ All sources failed, using fallback database")
        from pv_module_database import PV_MODULE_DATABASE
        from pv_module_database import module_to_dict
        all_modules = [module_to_dict(m) for m in PV_MODULE_DATABASE]
    
    # Deduplicate and filter
    all_modules = deduplicate_modules(all_modules)
    all_modules = filter_production_modules(all_modules)
    
    # Sort by manufacturer then power
    all_modules.sort(key=lambda x: (x['manufacturer'], -x['pdc0']))
    
    # Save to cache
    save_cache(all_modules, sources[0][0] if all_modules else "fallback")
    
    print(f"\n✅ Total: {len(all_modules)} production modules ready\n")
    
    return all_modules


def get_module_statistics(modules: List[Dict]) -> Dict:
    """Get statistics about the module database"""
    if not modules:
        return {}
    
    manufacturers = sorted(list(set(m['manufacturer'] for m in modules)))
    technologies = sorted(list(set(m['technology'] for m in modules)))
    
    return {
        "total_modules": len(modules),
        "manufacturers": manufacturers,
        "manufacturer_count": len(manufacturers),
        "technologies": technologies,
        "power_range": {
            "min": min(m['pdc0'] for m in modules),
            "max": max(m['pdc0'] for m in modules),
            "avg": sum(m['pdc0'] for m in modules) / len(modules)
        },
        "efficiency_range": {
            "min": min(m['efficiency'] for m in modules),
            "max": max(m['efficiency'] for m in modules),
            "avg": sum(m['efficiency'] for m in modules) / len(modules)
        },
        "last_updated": get_cache_metadata().get('last_updated', 'Unknown'),
        "source": get_cache_metadata().get('source', 'Unknown')
    }


def get_cache_metadata() -> Dict:
    """Get cache metadata"""
    if CACHE_METADATA.exists():
        with open(CACHE_METADATA, 'r') as f:
            return json.load(f)
    return {}


def clear_cache():
    """Clear the module cache"""
    if CACHE_FILE.exists():
        CACHE_FILE.unlink()
    if CACHE_METADATA.exists():
        CACHE_METADATA.unlink()
    print("✓ Cache cleared")


# ============================================================================
# CLI Interface
# ============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="PV Module Database Fetcher")
    parser.add_argument("--refresh", action="store_true", help="Force refresh from sources")
    parser.add_argument("--clear", action="store_true", help="Clear cache")
    parser.add_argument("--stats", action="store_true", help="Show database statistics")
    parser.add_argument("--export", type=str, help="Export to JSON file")
    
    args = parser.parse_args()
    
    if args.clear:
        clear_cache()
    else:
        modules = fetch_all_modules(force_refresh=args.refresh)
        
        if args.stats:
            stats = get_module_statistics(modules)
            print("\n" + "=" * 70)
            print("PV MODULE DATABASE STATISTICS")
            print("=" * 70)
            print(f"Total Modules: {stats['total_modules']}")
            print(f"Manufacturers: {stats['manufacturer_count']}")
            print(f"\nManufacturers: {', '.join(stats['manufacturers'][:15])}...")
            print(f"\nTechnologies: {', '.join(stats['technologies'])}")
            print(f"\nPower Range: {stats['power_range']['min']}W - {stats['power_range']['max']}W (avg: {stats['power_range']['avg']:.0f}W)")
            print(f"Efficiency Range: {stats['efficiency_range']['min']}% - {stats['efficiency_range']['max']}% (avg: {stats['efficiency_range']['avg']:.1f}%)")
            print(f"\nLast Updated: {stats['last_updated']}")
            print(f"Source: {stats['source']}")
            print("=" * 70)
        
        if args.export:
            with open(args.export, 'w') as f:
                json.dump(modules, f, indent=2, default=str)
            print(f"✓ Exported {len(modules)} modules to {args.export}")
