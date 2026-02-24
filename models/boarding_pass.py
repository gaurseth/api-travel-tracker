from typing import Optional, List
from pydantic import BaseModel, Field
from .common import ExtractedValue


class AirlineInfo(BaseModel):
    iata_code: ExtractedValue
    icao_code: Optional[ExtractedValue] = None
    name: Optional[ExtractedValue] = None


class PassengerInfo(BaseModel):
    full_name: ExtractedValue
    first_name: Optional[ExtractedValue] = None
    last_name: Optional[ExtractedValue] = None


class FlightInfo(BaseModel):
    flight_number: ExtractedValue
    airline_code: ExtractedValue
    operating_carrier: Optional[ExtractedValue] = None


class LocationInfo(BaseModel):
    iata: ExtractedValue
    city: Optional[ExtractedValue] = None


class RouteInfo(BaseModel):
    origin: LocationInfo
    destination: LocationInfo


class ScheduleInfo(BaseModel):
    """Flight schedule information with departure and arrival details."""
    departure_date: Optional[ExtractedValue] = None  # ISO-8601 yyyy-mm-dd
    departure_time: Optional[ExtractedValue] = None  # HH:MM (24-hour format)
    arrival_date: Optional[ExtractedValue] = None  # ISO-8601 yyyy-mm-dd
    arrival_time: Optional[ExtractedValue] = None  # HH:MM (24-hour format)


class BoardingInfo(BaseModel):
    time: Optional[ExtractedValue] = None  # Boarding time (HH:MM)
    gate: Optional[ExtractedValue] = None
    seat: Optional[ExtractedValue] = None
    group: Optional[ExtractedValue] = None


class BarcodeInfo(BaseModel):
    present: bool
    type: Optional[str] = None
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)


class FlightSegment(BaseModel):
    """
    Represents a single flight leg/segment on a boarding pass.

    A boarding pass can contain multiple segments (e.g., connecting flights).
    Each segment has its own route, schedule, flight details, and boarding information.
    """
    segment_number: int = Field(ge=1, description="Segment number (1, 2, 3...)")
    flight: FlightInfo
    route: RouteInfo
    schedule: Optional[ScheduleInfo] = None  # Departure/arrival dates and times
    boarding: Optional[BoardingInfo] = None  # Boarding time, gate, seat
    sequence_number: Optional[ExtractedValue] = None


class BoardingPass(BaseModel):
    """
    Complete boarding pass information supporting multi-segment passes.

    A boarding pass can contain:
    - Single segment: Direct flight (1 segment)
    - Multi-segment: Connecting flights on one boarding pass (2+ segments)

    Common information (passenger, airline, PNR) is stored at top level.
    Each segment has its own flight details, route, schedule, and boarding info.
    """
    # Common fields across all segments
    passenger: PassengerInfo
    airline: Optional[AirlineInfo] = None
    pnr: Optional[ExtractedValue] = None
    barcode: Optional[BarcodeInfo] = None
    raw_ocr_text: Optional[str] = None

    # Multi-segment support
    segments: List[FlightSegment] = Field(
        min_items=1,
        description="List of flight segments (1 for direct, 2+ for connecting flights)"
    )

    # Backward compatibility properties
    @property
    def is_multi_segment(self) -> bool:
        """Check if this boarding pass has multiple segments."""
        return len(self.segments) > 1

    @property
    def segment_count(self) -> int:
        """Total number of segments on this boarding pass."""
        return len(self.segments)

    # Convenience properties for single-segment passes (backward compatibility)
    @property
    def flight(self) -> Optional[FlightInfo]:
        """Get flight info from first segment (for backward compatibility)."""
        return self.segments[0].flight if self.segments else None

    @property
    def route(self) -> Optional[RouteInfo]:
        """Get route from first segment (for backward compatibility)."""
        return self.segments[0].route if self.segments else None

    @property
    def schedule(self) -> Optional[ScheduleInfo]:
        """Get schedule from first segment (for backward compatibility)."""
        return self.segments[0].schedule if self.segments else None

    @property
    def boarding(self) -> Optional[BoardingInfo]:
        """Get boarding info from first segment (for backward compatibility)."""
        return self.segments[0].boarding if self.segments else None
