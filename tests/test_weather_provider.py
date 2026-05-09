"""Tests for src/weather_provider.py — mocked HTTP, no live network calls."""
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import weather_provider  # noqa: E402


def _fake_payload(num_hours: int = 24):
    times = pd.date_range("2023-06-21", periods=num_hours, freq="h")
    return {
        "hourly": {
            "time": [t.isoformat() for t in times],
            "shortwave_radiation": [500.0] * num_hours,
            "direct_normal_irradiance": [600.0] * num_hours,
            "diffuse_radiation": [200.0] * num_hours,
            "temperature_2m": [25.0] * num_hours,
            "wind_speed_10m": [3.0] * num_hours,
        }
    }


@pytest.fixture
def isolated_cache(tmp_path, monkeypatch):
    """Redirect the on-disk cache to a tmp dir per test."""
    monkeypatch.setattr(weather_provider, "_CACHE_DIR", tmp_path)
    yield tmp_path


def test_fetch_weather_parses_response(isolated_cache):
    fake_response = type("R", (), {
        "json": lambda self: _fake_payload(8760),
        "raise_for_status": lambda self: None,
    })()
    with patch.object(weather_provider.requests, "get", return_value=fake_response):
        df = weather_provider.fetch_weather(-6.9, 107.6, "Asia/Jakarta", 2023)

    assert len(df) == 8760
    assert set(df.columns) == {"ghi", "dni", "dhi", "temp_air", "wind_speed"}
    assert df["ghi"].iloc[0] == 500.0
    assert df["temp_air"].iloc[0] == 25.0


def test_fetch_weather_uses_cache(isolated_cache):
    fake_response = type("R", (), {
        "json": lambda self: _fake_payload(48),
        "raise_for_status": lambda self: None,
    })()
    with patch.object(weather_provider.requests, "get", return_value=fake_response) as mock_get:
        weather_provider.fetch_weather(-6.9, 107.6, "Asia/Jakarta", 2023)
        weather_provider.fetch_weather(-6.9, 107.6, "Asia/Jakarta", 2023)
    assert mock_get.call_count == 1, "second call should hit cache, not HTTP"


def test_fallback_on_network_error(isolated_cache):
    sentinel_df = pd.DataFrame({"marker": [1]})

    def fallback():
        return sentinel_df

    with patch.object(
        weather_provider.requests,
        "get",
        side_effect=requests.ConnectionError("simulated"),
    ):
        df, source = weather_provider.fetch_weather_or_fallback(
            -6.9, 107.6, "Asia/Jakarta", 2023, fallback,
        )

    assert df is sentinel_df
    assert "synthetic" in source
    assert "ConnectionError" in source


def test_fallback_passes_through_on_success(isolated_cache):
    fake_response = type("R", (), {
        "json": lambda self: _fake_payload(8760),
        "raise_for_status": lambda self: None,
    })()
    with patch.object(weather_provider.requests, "get", return_value=fake_response):
        df, source = weather_provider.fetch_weather_or_fallback(
            -6.9, 107.6, "Asia/Jakarta", 2023, lambda: pd.DataFrame(),
        )
    assert source == "open-meteo"
    assert len(df) == 8760
