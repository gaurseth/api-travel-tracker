"""
Email Booking Normalizer.

Converts the email-parser Booking JSON format into the internal flat segment
dict format used by trip_service and dedup_service.

Email parser output schema (see ../email-parser/src/types.ts):
  {
    "airline": { "code": "EK", "name": "Emirates" },
    "pnr": "ABC123",
    "passengers": [{ "title": "MR", "firstName": "GAURAV", "lastName": "SETH", ... }],
    "flights": [{
        "flightNumber": "ET0850",
        "departureAirport": "DXB", "arrivalAirport": "JFK",
        "departureDate": "2026-01-10", "departureTime": "09:25",
        "arrivalDate": "2026-01-10", "arrivalTime": "16:45",
        "cabin": "Economy", "bookingClass": "V",
        "aircraft": "BOEING 787-9", ...
    }],
    ...
  }
"""
import re
from typing import Dict, Any, List, Optional


# Map full cabin names to single-letter codes
_CABIN_MAP = {
    "economy": "Y",
    "premium economy": "W",
    "business": "J",
    "first": "F",
}


def _normalize_flight_number(raw: Optional[str]) -> Optional[str]:
    """Extract digits from flight number. 'ET0850' -> '0850'."""
    if not raw:
        return None
    digits = re.sub(r"[^0-9]", "", raw)
    return digits if digits else None


def _map_cabin_class(cabin: Optional[str], booking_class: Optional[str]) -> Optional[str]:
    """
    Map cabin name or booking class letter to a single-letter code.
    booking_class (e.g. 'V', 'K') is more specific and takes precedence.
    """
    if booking_class and len(booking_class.strip()) == 1:
        return booking_class.strip().upper()
    if cabin:
        return _CABIN_MAP.get(cabin.strip().lower(), cabin[0].upper())
    return None


def _build_passenger_name(passengers: List[Dict[str, Any]]) -> Optional[str]:
    """
    Build 'LASTNAME/FIRSTNAME' from the first passenger entry.
    Strips title (MR, MRS, etc.) as that's handled by title logic.
    """
    if not passengers:
        return None
    pax = passengers[0]
    last = (pax.get("lastName") or "").strip().upper()
    first = (pax.get("firstName") or "").strip().upper()
    if last and first:
        return f"{last}/{first}"
    return last or first or None


def normalize_email_booking(booking: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Convert an email-parser Booking payload into a list of internal
    segment dicts ready for dedup_service.ingest_segments().

    Each segment gets source='email' and includes fields that only
    email provides (ticket_number, aircraft, terminals).
    """
    airline = booking.get("airline") or {}
    airline_code = airline.get("code")
    pnr = booking.get("pnr") or booking.get("bookingReference")
    passengers = booking.get("passengers") or []
    flights = booking.get("flights") or []

    passenger_name = _build_passenger_name(passengers)
    ticket_number = None
    if passengers:
        ticket_number = passengers[0].get("ticketNumber")

    segments: List[Dict[str, Any]] = []

    for flight in flights:
        seg: Dict[str, Any] = {
            # Route
            "origin": (flight.get("departureAirport") or "").strip().upper() or None,
            "destination": (flight.get("arrivalAirport") or "").strip().upper() or None,

            # Flight
            "airline_code": airline_code,
            "flight_number": _normalize_flight_number(flight.get("flightNumber")),

            # Schedule
            "departure_date": flight.get("departureDate"),
            "departure_time": flight.get("departureTime"),
            "arrival_date": flight.get("arrivalDate"),
            "arrival_time": flight.get("arrivalTime"),

            # Boarding (email usually doesn't have these)
            "seat": None,
            "gate": None,
            "boarding_time": None,

            # Booking
            "pnr": pnr,
            "cabin_class": _map_cabin_class(
                flight.get("cabin"), flight.get("bookingClass")
            ),
            "ticket_number": ticket_number,

            # Email-specific enrichment fields
            "aircraft": flight.get("aircraft"),
            "departure_terminal": flight.get("departureTerminal"),
            "arrival_terminal": flight.get("arrivalTerminal"),

            # Identity
            "passenger_name": passenger_name,
            "passenger_id": None,

            # Provenance
            "source": "email",
            "conflict_log": [],
        }

        # Check for per-passenger seat assignment
        if passengers:
            pax_seat = passengers[0].get("seat")
            if pax_seat:
                seg["seat"] = pax_seat.strip().upper()

        segments.append(seg)

    return segments
