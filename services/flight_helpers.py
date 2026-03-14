"""
Flight helper functions: distance, trip type, and travel time estimation.

Uses data/airports.json for airport coordinates and country info.
"""

import json
import math
import os
from typing import Optional, Tuple

# ---------------------------------------------------------------------------
# Airport data cache (loaded once at module import)
# ---------------------------------------------------------------------------

_AIRPORTS: dict = {}  # keyed by IATA code


def _load_airports() -> dict:
    """Load airports.json into a dict keyed by IATA code."""
    data_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "data", "airports.json"
    )
    with open(data_path, "r") as f:
        airports_list = json.load(f)
    return {a["iata"]: a for a in airports_list if a.get("iata")}


_AIRPORTS = _load_airports()

# ---------------------------------------------------------------------------
# Distance-based cruise speed tiers (mph)
# ---------------------------------------------------------------------------

_SPEED_TIERS = [
    (200, 350),    # < 200 mi  → 350 mph (regional / turboprop)
    (1000, 400),   # 200–1000  → 400 mph (short-haul jet)
    (4000, 500),   # 1000–4000 → 500 mph (medium-haul)
    (float("inf"), 550),  # 4000+  → 550 mph (long-haul cruise)
]

_OVERHEAD_MINUTES = 5  # taxi, takeoff, descent, landing


# ---------------------------------------------------------------------------
# Haversine
# ---------------------------------------------------------------------------

def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in miles between two lat/lon points."""
    R = 3958.8  # Earth radius in miles

    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))

    return R * c


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def _get_airport(iata: str) -> Optional[dict]:
    """Look up an airport by IATA code (case-insensitive)."""
    return _AIRPORTS.get(iata.upper())


def estimate_flight_distance(origin_iata: str, destination_iata: str) -> Optional[float]:
    """
    Estimate flight distance in miles between two airports.

    Uses haversine formula + 8 % margin for non-straight routing.
    Returns None if either airport code is not found.
    """
    origin = _get_airport(origin_iata)
    dest = _get_airport(destination_iata)
    if not origin or not dest:
        return None

    gc_distance = _haversine(origin["lat"], origin["long"], dest["lat"], dest["long"])
    return round(gc_distance * 1.02, 1)  # +2 % routing margin


def get_trip_type(origin_iata: str, destination_iata: str) -> str:
    """
    Return 'international', 'domestic', or 'unknown' based on whether
    the origin and destination airports are in different countries.
    """
    origin = _get_airport(origin_iata)
    dest = _get_airport(destination_iata)
    if not origin or not dest:
        return "unknown"

    if origin["country"] == dest["country"]:
        return "domestic"
    return "international"


def estimate_travel_time(origin_iata: str, destination_iata: str) -> Optional[int]:
    """
    Estimate total travel time in minutes between two airports.

    Uses distance-based speed tiers for cruise speed plus a fixed
    30-minute overhead for taxi, takeoff, descent, and landing.
    Returns None if either airport code is not found.
    """
    distance = estimate_flight_distance(origin_iata, destination_iata)
    if distance is None:
        return None

    # Pick cruise speed based on distance tier
    cruise_speed = 500  # default fallback
    for threshold, speed in _SPEED_TIERS:
        if distance < threshold:
            cruise_speed = speed
            break

    cruise_minutes = (distance / cruise_speed) * 60
    total = round(cruise_minutes + _OVERHEAD_MINUTES)
    return total
