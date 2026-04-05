"""
Aviationstack API client for flight schedule lookups.

Enriches trip segments with real departure/arrival times and timezone data
when times are missing from extraction or manual entry.
"""
import os
import re
from datetime import datetime
from typing import Any, Dict, Optional

import requests
from zoneinfo import ZoneInfo


_API_BASE = "http://api.aviationstack.com/v1/flights"
_TIMEOUT = 10  # seconds


def _is_enabled() -> bool:
    return os.getenv("AVIATIONSTACK_ENABLED", "false").lower() == "true"


def _get_api_key() -> Optional[str]:
    return os.getenv("AVIATIONSTACK_API_KEY")


def _build_flight_iata(airline_code: str, flight_number: str) -> str:
    """
    Build the flight_iata param (e.g. 'EK202').
    Handles cases where flight_number already includes the airline prefix.
    """
    digits = re.sub(r"[^0-9]", "", flight_number).lstrip("0")
    # If flight_number already starts with airline_code, strip leading zeros from the numeric part
    if flight_number.upper().startswith(airline_code.upper()):
        prefix = airline_code.upper()
        num_part = re.sub(r"[^0-9]", "", flight_number[len(prefix):]).lstrip("0")
        return f"{prefix}{num_part}"
    return f"{airline_code.upper()}{digits}"


def _parse_local_time(
    scheduled_iso: str, timezone_str: str
) -> Optional[Dict[str, str]]:
    """
    Parse an ISO-8601 scheduled time and convert to local airport time.
    Returns {"time": "HH:MM", "date": "YYYY-MM-DD"} or None.
    """
    try:
        dt_utc = datetime.fromisoformat(scheduled_iso)
        tz = ZoneInfo(timezone_str)
        dt_local = dt_utc.astimezone(tz)
        return {
            "time": dt_local.strftime("%H:%M"),
            "date": dt_local.strftime("%Y-%m-%d"),
        }
    except Exception:
        return None


def _parse_time_naive(scheduled_iso: str) -> Optional[Dict[str, str]]:
    """
    Parse an ISO-8601 time without timezone conversion.
    Extracts HH:MM and date directly from the string.
    """
    try:
        dt = datetime.fromisoformat(scheduled_iso)
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
    Look up a flight's schedule from the Aviationstack API.

    Returns enrichment data dict or None if lookup fails/disabled.
    """
    print(f"[Aviationstack] lookup_flight_schedule called: airline={airline_code}, flight={flight_number}, origin={origin}, dest={destination}")

    if not _is_enabled():
        print("[Aviationstack] SKIPPED — AVIATIONSTACK_ENABLED is not true")
        return None

    api_key = _get_api_key()
    if not api_key:
        print("[Aviationstack] SKIPPED — AVIATIONSTACK_API_KEY not set")
        return None

    flight_iata = _build_flight_iata(airline_code, flight_number)
    print(f"[Aviationstack] Built flight_iata: {flight_iata}")

    params: Dict[str, str] = {
        "access_key": api_key,
        "flight_iata": flight_iata,
    }
    if origin:
        params["dep_iata"] = origin.upper()
    if destination:
        params["arr_iata"] = destination.upper()

    print(f"[Aviationstack] Request params (excluding key): flight_iata={flight_iata}, dep_iata={params.get('dep_iata')}, arr_iata={params.get('arr_iata')}")

    try:
        resp = requests.get(_API_BASE, params=params, timeout=_TIMEOUT)
        print(f"[Aviationstack] HTTP {resp.status_code}")
        resp.raise_for_status()
        data = resp.json()

        # Log error object if present
        if "error" in data:
            print(f"[Aviationstack] API error: {data['error']}")
            return None

        flights = data.get("data")
        print(f"[Aviationstack] Flights returned: {len(flights) if flights else 0}")

        if not flights:
            print(f"[Aviationstack] No flights found. Full response: {data}")
            return None

        # Use the first result
        flight = flights[0]
        print(f"[Aviationstack] Using first flight: {flight.get('flight', {}).get('iata')} | status: {flight.get('flight_status')}")

        dep = flight.get("departure", {})
        arr = flight.get("arrival", {})

        dep_scheduled = dep.get("scheduled")
        dep_timezone = dep.get("timezone")
        arr_scheduled = arr.get("scheduled")
        arr_timezone = arr.get("timezone")

        print(f"[Aviationstack] Departure: scheduled={dep_scheduled}, tz={dep_timezone}, iata={dep.get('iata')}")
        print(f"[Aviationstack] Arrival:   scheduled={arr_scheduled}, tz={arr_timezone}, iata={arr.get('iata')}")

        result: Dict[str, Any] = {
            "departure_time": None,
            "arrival_time": None,
            "arrival_date": None,
            "departure_timezone": dep_timezone,  # may be None
            "arrival_timezone": arr_timezone,     # may be None
        }

        # Parse departure time — use timezone if available, else extract from ISO string directly
        if dep_scheduled:
            if dep_timezone:
                dep_local = _parse_local_time(dep_scheduled, dep_timezone)
            else:
                dep_local = _parse_time_naive(dep_scheduled)
            if dep_local:
                result["departure_time"] = dep_local["time"]

        # Parse arrival time
        if arr_scheduled:
            if arr_timezone:
                arr_local = _parse_local_time(arr_scheduled, arr_timezone)
            else:
                arr_local = _parse_time_naive(arr_scheduled)
            if arr_local:
                result["arrival_time"] = arr_local["time"]
                result["arrival_date"] = arr_local["date"]

        # Return if we got at least one useful time
        if result["departure_time"] or result["arrival_time"]:
            print(f"[Aviationstack] SUCCESS — returning: {result}")
            return result

        print("[Aviationstack] No usable times found in response — returning None")
        return None

    except Exception as e:
        print(f"[Aviationstack] EXCEPTION for {flight_iata}: {type(e).__name__}: {e}")
        return None
