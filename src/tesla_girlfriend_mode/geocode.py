"""Address → coordinates via OpenStreetMap's free Nominatim service.

Owners type a place name + street address in the setup wizard; nobody
should ever have to type latitude/longitude. Used once at setup time.
"""
from __future__ import annotations

import requests

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"


def geocode_address(address: str, timeout: float = 10.0) -> tuple[float, float] | None:
    """Return (lat, lon) for a street address, or None if not found."""
    if not address or not address.strip():
        return None
    try:
        resp = requests.get(
            NOMINATIM_URL,
            params={"q": address, "format": "json", "limit": 1},
            headers={"User-Agent": "tesla-girlfriend-mode/0.1.0"},
            timeout=timeout)
        resp.raise_for_status()
        hits = resp.json()
    except Exception:
        return None
    if not hits:
        return None
    try:
        return float(hits[0]["lat"]), float(hits[0]["lon"])
    except (KeyError, ValueError, TypeError):
        return None
