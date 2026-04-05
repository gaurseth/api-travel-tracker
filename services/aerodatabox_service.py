"""
AeroDataBox API client for flight schedule lookups.

Enriches trip segments with real departure/arrival times
when times are missing from extraction or manual entry.

API docs: https://doc.aerodatabox.com/
"""
import os
import re
from datetime import datetime
from typing import Any, Dict, Optional

import requests


_API_BASE = "https://prod.api.market/api/v1/aedbx/aerodatabox"
_TIMEOUT = 10  # seconds


def _is_enabled() -> bool:
    return os.getenv("AERODATABOX_ENABLED", "false").lower() == "true"


def _get_api_key() -> Optional[str]:
    return os.getenv("AERODATABOX_API_KEY")


def _build_flight_iata(airline_code: str, flight_number: str) -> str:
    """
    Build the flight number string (e.g. 'EK202').
    Handles cases where flight_number already includes the airline prefix.
    """
    digits = re.sub(r"[^0-9]", "", flight_number).lstrip("0")
    if flight_number.upper().startswith(airline_code.upper()):
        prefix = airline_code.upper()
        num_part = re.sub(r"[^0-9]", "", flight_number[len(prefix):]).lstrip("0")
        return f"{prefix}{num_part}"
    return f"{airline_code.upper()}{digits}"


def _parse_local_time(local_iso: str) -> Optional[Dict[str, str]]:
    """
    Parse a local time string from AeroDataBox response.
    AeroDataBox returns times in local airport time already.
    Format: "2026-01-10 09:25" or ISO-8601 variants.
    Returns {"time": "HH:MM", "date": "YYYY-MM-DD"} or None.
    """
    try:
        # Handle both "2026-01-10T09:25+04:00" and "2026-01-10 09:25" formats
        cleaned = local_iso.replace("T", " ").split("+")[0].split("Z")[0].strip()
        dt = datetime.fromisoformat(cleaned)
        return {
            "time": dt.strftime("%H:%M"),
            "date": dt.strftime("%Y-%m-%d"),
        }
    except Exception:
        return None


def lookup_flight_schedule(
    airline_code: str,
    flight_number: str,
    origin: Optional[str] = None,
    destination: Optional[str] = None,
    departure_date: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Look up a flight's schedule from the AeroDataBox API.

    Uses the Flight Status endpoint:
        GET /flights/number/{flightNumber}/{date}

    Returns enrichment data dict or None if lookup fails/disabled.
    """
    print(f"[AeroDataBox] lookup_flight_schedule called: airline={airline_code}, "
          f"flight={flight_number}, origin={origin}, dest={destination}, date={departure_date}")

    if not _is_enabled():
        print("[AeroDataBox] SKIPPED — AERODATABOX_ENABLED is not true")
        return None

    api_key = _get_api_key()
    if not api_key:
        print("[AeroDataBox] SKIPPED — AERODATABOX_API_KEY not set")
        return None

    flight_iata = _build_flight_iata(airline_code, flight_number)
    print(f"[AeroDataBox] Built flight_iata: {flight_iata}")

    # Build the endpoint URL
    # If we have a departure date, use the date-specific endpoint
    if departure_date:
        date_str = departure_date
    else:
        date_str = datetime.utcnow().strftime("%Y-%m-%d")

    url = f"{_API_BASE}/flights/number/{flight_iata}/{date_str}"

    headers = {
        "x-api-market-key": api_key,
    }

    print(f"[AeroDataBox] GET {url}")

    try:
        resp = requests.get(url, headers=headers, timeout=_TIMEOUT)
        print(f"[AeroDataBox] HTTP {resp.status_code}")
        resp.raise_for_status()
        flights = resp.json()

        if not isinstance(flights, list) or not flights:
            print(f"[AeroDataBox] No flights found. Response: {str(flights)[:500]}")
            return None

        # Find the best matching flight (by origin/destination if provided)
        flight = None
        for f in flights:
            dep_iata = f.get("departure", {}).get("airport", {}).get("iata")
            arr_iata = f.get("arrival", {}).get("airport", {}).get("iata")
            if origin and dep_iata and dep_iata.upper() != origin.upper():
                continue
            if destination and arr_iata and arr_iata.upper() != destination.upper():
                continue
            flight = f
            break

        if not flight:
            # Fallback to first result if no exact match
            flight = flights[0]
            print(f"[AeroDataBox] No exact route match, using first result")

        dep = flight.get("departure", {})
        arr = flight.get("arrival", {})

        # AeroDataBox provides scheduledTimeLocal in local airport time
        dep_scheduled = dep.get("scheduledTimeLocal") or dep.get("scheduledTime")
        arr_scheduled = arr.get("scheduledTimeLocal") or arr.get("scheduledTime")

        dep_airport = dep.get("airport", {}).get("iata")
        arr_airport = arr.get("arrival", {}).get("airport", {}).get("iata") if not arr.get("airport") else arr.get("airport", {}).get("iata")

        print(f"[AeroDataBox] Departure: scheduled={dep_scheduled}, airport={dep_airport}")
        print(f"[AeroDataBox] Arrival:   scheduled={arr_scheduled}, airport={arr_airport}")

        result: Dict[str, Any] = {
            "departure_time": None,
            "arrival_time": None,
            "arrival_date": None,
            "departure_timezone": dep.get("timezone"),
            "arrival_timezone": arr.get("timezone"),
        }

        # Parse departure time (already in local time)
        if dep_scheduled:
            dep_local = _parse_local_time(dep_scheduled)
            if dep_local:
                result["departure_time"] = dep_local["time"]

        # Parse arrival time (already in local time)
        if arr_scheduled:
            arr_local = _parse_local_time(arr_scheduled)
            if arr_local:
                result["arrival_time"] = arr_local["time"]
                result["arrival_date"] = arr_local["date"]

        # Return if we got at least one useful time
        if result["departure_time"] or result["arrival_time"]:
            print(f"[AeroDataBox] SUCCESS — returning: {result}")
            return result

        print("[AeroDataBox] No usable times found in response — returning None")
        return None

    except Exception as e:
        print(f"[AeroDataBox] EXCEPTION for {flight_iata}: {type(e).__name__}: {e}")
        return None
