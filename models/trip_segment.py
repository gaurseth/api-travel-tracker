"""
Trip Segment Model

Represents a single flight leg/segment within a trip.
A trip can contain multiple segments (e.g., outbound connections, return journey).
"""
from typing import Optional, Literal, List, Dict, Any
from pydantic import BaseModel, Field


class TripSegment(BaseModel):
    """
    Represents a single flight segment within a trip.

    A segment can be:
    - Created from a boarding pass scan
    - Manually entered by the user
    - Part of a multi-segment boarding pass
    - An outward or return leg of the overall trip
    """
    segment_number: int = Field(ge=1, description="Segment number within the trip (1, 2, 3...)")

    # Journey direction — used to compute trip-level origin/destination/dates
    journey_type: Literal["outward", "return"] = Field(
        default="outward",
        description=(
            "Whether this segment is part of the outward or return journey. "
            "Trip-level origin/destination/dates are derived from outward segments only."
        )
    )

    # Route information
    origin: Optional[str] = Field(None, description="Origin airport IATA code (e.g., 'DXB')")
    destination: Optional[str] = Field(None, description="Destination airport IATA code (e.g., 'JFK')")

    # Schedule information
    departure_date: Optional[str] = Field(None, description="Departure date (ISO-8601: yyyy-mm-dd)")
    departure_time: Optional[str] = Field(None, description="Departure time (HH:MM, 24-hour format)")
    arrival_date: Optional[str] = Field(None, description="Arrival date (ISO-8601: yyyy-mm-dd)")
    arrival_time: Optional[str] = Field(None, description="Arrival time (HH:MM, 24-hour format)")

    # Flight information
    airline_code: Optional[str] = Field(None, description="Airline IATA code (e.g., 'EK', 'AA')")
    flight_number: Optional[str] = Field(None, description="Flight number (e.g., 'EK202')")
    operating_carrier: Optional[str] = Field(None, description="Operating carrier if codeshare")

    # Booking
    pnr: Optional[str] = Field(None, description="PNR / booking reference code")
    cabin_class: Optional[str] = Field(None, description="Cabin class code (e.g., 'Y', 'J', 'F')")
    ticket_number: Optional[str] = Field(None, description="E-ticket number (e.g., '0712158238861')")
    aircraft: Optional[str] = Field(None, description="Aircraft type (e.g., 'BOEING 787-9 JET')")

    # Terminal information (from email confirmations)
    departure_terminal: Optional[str] = Field(None, description="Departure terminal (e.g., 'TERMINAL 2')")
    arrival_terminal: Optional[str] = Field(None, description="Arrival terminal (e.g., 'TERMINAL 3')")

    # Boarding information
    seat: Optional[str] = Field(None, description="Seat assignment (e.g., '12A')")
    gate: Optional[str] = Field(None, description="Gate number (e.g., 'A12')")
    boarding_time: Optional[str] = Field(None, description="Boarding time (HH:MM)")

    # Boarding pass reference
    boarding_pass_id: Optional[str] = Field(
        None,
        description="References boarding pass in trip.boarding_passes array"
    )
    segment_index_in_pass: Optional[int] = Field(
        None,
        ge=0,
        description="Index of this segment within the boarding pass (0, 1, 2...)"
    )

    # Passenger
    passenger_name: Optional[str] = Field(None, description="Passenger name for this segment")
    passenger_id: Optional[str] = Field(None, description="References passenger in users/{userId}/passengers/{passengerId}")

    # Computed flight info
    distance_miles: Optional[float] = Field(None, description="Estimated flight distance in miles")
    travel_duration_minutes: Optional[int] = Field(None, description="Estimated travel time in minutes")
    segment_type: Optional[str] = Field(None, description="'international' or 'domestic' based on origin/destination countries")

    # Timezone info (from Aviationstack API enrichment)
    departure_timezone: Optional[str] = Field(None, description="IANA timezone, e.g. 'America/New_York'")
    arrival_timezone: Optional[str] = Field(None, description="IANA timezone, e.g. 'Europe/London'")

    # Provenance
    source: Optional[str] = Field(
        None,
        description="Data source: 'boarding_pass', 'manual', or 'email'"
    )
    conflict_log: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Log of field conflicts during multi-source merge"
    )

    # Metadata
    manually_entered: bool = Field(
        default=False,
        description="True if segment was manually created (not from boarding pass scan)"
    )
    notes: Optional[str] = Field(None, description="User notes for this segment")

    class Config:
        json_schema_extra = {
            "example": {
                "segment_number": 1,
                "journey_type": "outward",
                "origin": "DXB",
                "destination": "JFK",
                "departure_date": "2026-03-15",
                "departure_time": "10:30",
                "arrival_date": "2026-03-15",
                "arrival_time": "16:45",
                "airline_code": "EK",
                "flight_number": "EK202",
                "seat": "12A",
                "gate": "A7",
                "boarding_time": "09:30",
                "boarding_pass_id": "bp_abc123",
                "segment_index_in_pass": 0,
                "distance_miles": 7013.2,
                "travel_duration_minutes": 872,
                "segment_type": "international",
                "manually_entered": False
            }
        }
