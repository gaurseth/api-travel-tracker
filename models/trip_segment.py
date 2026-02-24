"""
Trip Segment Model

Represents a single flight leg/segment within a trip.
A trip can contain multiple segments (e.g., outbound, return, connections).
"""
from typing import Optional
from pydantic import BaseModel, Field


class TripSegment(BaseModel):
    """
    Represents a single flight segment within a trip.

    A segment can be:
    - Created from a boarding pass scan
    - Manually entered by the user
    - Part of a multi-segment boarding pass
    """
    segment_number: int = Field(ge=1, description="Segment number within the trip (1, 2, 3...)")

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
                "manually_entered": False
            }
        }
