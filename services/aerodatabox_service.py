"""
AeroDataBox API client for flight schedule lookups.

Enriches trip segments with real departure/arrival times
when times are missing from extraction or manual entry.

API docs: https://doc.aerodatabox.com/
"""
import os
import re
from datetime import datetime, timedelta, date
from typing import Any, Dict, Optional

import requests

_MAX_HISTORY_DAYS = 180


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


def _extract_local_time(leg: Dict[str, Any]) -> Optional[str]:
    """
    Extract the local scheduled time string from a departure/arrival dict.
    Handles both formats:
      - "scheduledTimeLocal": "2025-11-08 13:50+01:00"  (plain string)
      - "scheduledTime": {"utc": "...", "local": "..."}  (nested dict)
    """
    # Try direct string field first
    val = leg.get("scheduledTimeLocal")
    if isinstance(val, str):
        return val

    # Try nested dict
    val = leg.get("scheduledTime")
    if isinstance(val, dict):
        return val.get("local") or val.get("utc")
    if isinstance(val, str):
        return val

    return None


def _is_beyond_history_limit(departure_date: str) -> bool:
    """Check if the departure date is more than 180 days in the past."""
    try:
        dep = date.fromisoformat(departure_date)
        cutoff = date.today() - timedelta(days=_MAX_HISTORY_DAYS)
        return dep < cutoff
    except (ValueError, TypeError):
        return False


def _make_dummy_date(departure_date: str) -> str:
    """
    Create a dummy date ~5 months ago from today, on the same day of the week
    as the original departure date. This lets us query the API for the same
    flight's schedule (airlines keep the same weekday pattern).
    """
    original = date.fromisoformat(departure_date)
    target_weekday = original.weekday()  # 0=Mon, 6=Sun

    # Start from 5 months ago
    candidate = date.today() - timedelta(days=150)

    # Shift to match the same weekday
    diff = (target_weekday - candidate.weekday()) % 7
    candidate += timedelta(days=diff)

    return candidate.isoformat()


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
    used_dummy = False
    original_departure_date = departure_date
    if departure_date:
        if _is_beyond_history_limit(departure_date):
            dummy = _make_dummy_date(departure_date)
            print(f"[AeroDataBox] Date {departure_date} is >180 days old, using dummy date {dummy} (same weekday)")
            date_str = dummy
            used_dummy = True
        else:
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

        # AeroDataBox returns times as either:
        #   "scheduledTimeLocal": "2025-11-08 13:50+01:00"  (string)
        #   "scheduledTime": {"utc": "...", "local": "..."}  (dict)
        dep_scheduled = _extract_local_time(dep)
        arr_scheduled = _extract_local_time(arr)

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

        # When using a dummy date, compute arrival_date from the day difference
        # between the API's dep/arr dates applied to the original departure date.
        # e.g. API says dep=Nov 8, arr=Nov 9 (diff=1) → real arr = original dep + 1 day
        if used_dummy and original_departure_date and dep_scheduled and arr_scheduled:
            dep_parsed = _parse_local_time(dep_scheduled)
            arr_parsed = _parse_local_time(arr_scheduled)
            if dep_parsed and arr_parsed:
                api_dep_date = date.fromisoformat(dep_parsed["date"])
                api_arr_date = date.fromisoformat(arr_parsed["date"])
                day_diff = (api_arr_date - api_dep_date).days
                real_arr_date = date.fromisoformat(original_departure_date) + timedelta(days=day_diff)
                result["arrival_date"] = real_arr_date.isoformat()
                print(f"[AeroDataBox] Dummy date correction: API dep={dep_parsed['date']} arr={arr_parsed['date']} "
                      f"diff={day_diff}d → real arrival_date={result['arrival_date']}")

        # Return if we got at least one useful time
        if result["departure_time"] or result["arrival_time"]:
            print(f"[AeroDataBox] SUCCESS — returning: {result}")
            return result

        print("[AeroDataBox] No usable times found in response — returning None")
        return None

    except Exception as e:
        print(f"[AeroDataBox] EXCEPTION for {flight_iata}: {type(e).__name__}: {e}")
        return None


def search_flight(
    flight_number: str,
    departure_date: str,
) -> Optional[Dict[str, Any]]:
    """
    Search for a flight by number and date using AeroDataBox.

    Uses: GET /flights/{searchBy}/{searchParam}?dateLocalRole=departure

    Args:
        flight_number: e.g. "UA46", "EK202"
        departure_date: ISO date e.g. "2026-04-09"

    Returns:
        Dict with origin, destination, departure_time, arrival_time,
        arrival_date, departure_date, airline_code, flight_number, aircraft
        or None if not found.
    """
    if not _is_enabled():
        return None

    api_key = _get_api_key()
    if not api_key:
        return None

    # Clean flight number: uppercase, strip spaces
    flight_num = flight_number.strip().upper()

    # Use dummy date if beyond history limit
    if _is_beyond_history_limit(departure_date):
        query_date = _make_dummy_date(departure_date)
        used_dummy = True
        print(f"[AeroDataBox:search] Date {departure_date} is >180 days old, using dummy {query_date}")
    else:
        query_date = departure_date
        used_dummy = False

    url = f"{_API_BASE}/flights/number/{flight_num}/{query_date}"
    headers = {"x-api-market-key": api_key}
    params = {"dateLocalRole": "departure"}

    print(f"[AeroDataBox:search] GET {url} params={params}")

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=_TIMEOUT)
        print(f"[AeroDataBox:search] HTTP {resp.status_code}")
        resp.raise_for_status()
        flights = resp.json()

        if not isinstance(flights, list) or not flights:
            print(f"[AeroDataBox:search] No flights found")
            return None

        # Use first result
        flight = flights[0]

        dep = flight.get("departure", {})
        arr = flight.get("arrival", {})

        dep_time_str = _extract_local_time(dep)
        arr_time_str = _extract_local_time(arr)

        dep_parsed = _parse_local_time(dep_time_str) if dep_time_str else None
        arr_parsed = _parse_local_time(arr_time_str) if arr_time_str else None

        # Compute correct arrival date when using dummy
        arrival_date = arr_parsed["date"] if arr_parsed else None
        if used_dummy and dep_parsed and arr_parsed:
            api_dep = date.fromisoformat(dep_parsed["date"])
            api_arr = date.fromisoformat(arr_parsed["date"])
            day_diff = (api_arr - api_dep).days
            arrival_date = (date.fromisoformat(departure_date) + timedelta(days=day_diff)).isoformat()

        # Extract aircraft info
        aircraft_raw = flight.get("aircraft", {})
        aircraft = None
        if aircraft_raw:
            model = aircraft_raw.get("model") or aircraft_raw.get("modelText")
            reg = aircraft_raw.get("reg")
            aircraft = {"model": model, "registration": reg}

        # Extract airline info
        airline_raw = flight.get("airline", {})

        result = {
            "flight_number": flight_num,
            "airline_code": airline_raw.get("iata"),
            "airline_name": airline_raw.get("name"),
            "origin": dep.get("airport", {}).get("iata"),
            "origin_name": dep.get("airport", {}).get("name"),
            "destination": arr.get("airport", {}).get("iata"),
            "destination_name": arr.get("airport", {}).get("name"),
            "departure_date": departure_date,
            "departure_time": dep_parsed["time"] if dep_parsed else None,
            "arrival_date": arrival_date,
            "arrival_time": arr_parsed["time"] if arr_parsed else None,
            "aircraft": aircraft,
        }

        print(f"[AeroDataBox:search] SUCCESS — {result.get('origin')}->{result.get('destination')}")
        return result

    except Exception as e:
        print(f"[AeroDataBox:search] EXCEPTION: {type(e).__name__}: {e}")
        return None
