"""
Real-weather provider using the Open-Meteo Archive API.

Falls back to a caller-supplied synthetic generator if the network call
fails, so that the GUI keeps working offline. Successful responses are
cached on disk under ``data/weather_cache/`` (one parquet per
lat/lon/year) — Open-Meteo is free and rate-limited but caching keeps
repeated runs instant.

Open-Meteo Archive API: https://open-meteo.com/en/docs/historical-weather-api
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Optional

import pandas as pd
import requests

_API_URL = "https://archive-api.open-meteo.com/v1/archive"
_CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "weather_cache"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger(__name__)


def _cache_path(latitude: float, longitude: float, year: int) -> Path:
    safe = f"{latitude:.4f}_{longitude:.4f}_{year}.parquet"
    return _CACHE_DIR / safe


def fetch_weather(
    latitude: float,
    longitude: float,
    timezone: str = "Asia/Jakarta",
    year: int = 2023,
    timeout_seconds: float = 30.0,
) -> pd.DataFrame:
    """Fetch one full year of hourly weather from Open-Meteo Archive.

    Returns a DataFrame indexed by tz-aware timestamps with the same column
    schema as ``gui.generate_synthetic_weather``: ghi, dni, dhi, temp_air,
    wind_speed.
    """
    cached = _cache_path(latitude, longitude, year)
    if cached.exists():
        logger.info("loading cached weather from %s", cached)
        return pd.read_parquet(cached)

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": f"{year}-01-01",
        "end_date": f"{year}-12-31",
        "hourly": ",".join([
            "shortwave_radiation",
            "direct_normal_irradiance",
            "diffuse_radiation",
            "temperature_2m",
            "wind_speed_10m",
        ]),
        "timezone": timezone,
    }
    response = requests.get(_API_URL, params=params, timeout=timeout_seconds)
    response.raise_for_status()
    payload = response.json()

    hourly = payload["hourly"]
    df = pd.DataFrame({
        "ghi": hourly["shortwave_radiation"],
        "dni": hourly["direct_normal_irradiance"],
        "dhi": hourly["diffuse_radiation"],
        "temp_air": hourly["temperature_2m"],
        "wind_speed": hourly["wind_speed_10m"],
    }, index=pd.to_datetime(hourly["time"]).tz_localize(timezone))

    df.to_parquet(cached)
    logger.info("cached weather to %s (%d rows)", cached, len(df))
    return df


def fetch_weather_or_fallback(
    latitude: float,
    longitude: float,
    timezone: str,
    year: int,
    fallback: Callable[[], pd.DataFrame],
) -> tuple[pd.DataFrame, str]:
    """Try real weather, fall back to ``fallback`` callable on any failure.

    Returns ``(weather_df, source)`` where source is either
    ``"open-meteo"`` or ``"synthetic (network failure)"``.
    """
    try:
        return fetch_weather(latitude, longitude, timezone, year), "open-meteo"
    except (requests.RequestException, KeyError, ValueError) as exc:
        logger.warning("real-weather fetch failed (%s); falling back to synthetic", exc)
        return fallback(), f"synthetic (network failure: {type(exc).__name__})"
