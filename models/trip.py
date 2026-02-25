"""
Trip model - represents a travel trip with multi-segment support.
"""
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime
from .trip_segment import TripSegment
from .boarding_pass_attachment import BoardingPassAttachment


class TripMetadata(BaseModel):
    """Metadata about trip creation and modifications."""
    created_at: datetime
    updated_at: datetime
    source: str = Field(default="manual")  # manual | boarding_pass_scan | api
    extraction_metadata: Optional[dict] = None  # Only present if from boarding pass scan


class Trip(BaseModel):
    """
    A trip represents a journey with support for multiple segments.

    Architecture:
    - segments: All flight legs across outward and return journeys
    - boarding_passes: Raw boarding pass data stored once at trip level
    - Each segment references its boarding pass via boarding_pass_id

    Derived fields (origin, destination, departure_date, arrival_date):
    - Computed from outward segments only
    - origin/departure_date → first outward segment
    - destination/arrival_date → last outward segment
    - Stored in Firestore for querying but never set by the user directly
    """
    trip_id: str
    user_id: str
    tenant_id: str = Field(default="personal")
    trip_type: str = Field(default="flight")  # flight | train | bus | car | hotel | other

    # Core data
    segments: List[TripSegment] = Field(
        default_factory=list,
        description="All flight legs — outward and return"
    )
    boarding_passes: List[BoardingPassAttachment] = Field(
        default_factory=list,
        description="Boarding passes attached to this trip (stored once, referenced by segments)"
    )

    # Passenger info
    passenger_name: Optional[str] = None

    # Derived fields — computed from outward segments, stored for Firestore querying.
    # Never set directly by the user; always populated by TripService.
    origin: Optional[str] = Field(
        None,
        description="Derived: first outward segment origin (IATA code)"
    )
    destination: Optional[str] = Field(
        None,
        description="Derived: last outward segment destination (IATA code)"
    )
    departure_date: Optional[str] = Field(
        None,
        description="Derived: first outward segment departure date (ISO-8601)"
    )
    arrival_date: Optional[str] = Field(
        None,
        description="Derived: last outward segment arrival date (ISO-8601)"
    )

    # User-added fields
    title: Optional[str] = None
    description: Optional[str] = None
    notes: Optional[str] = None
    tags: List[str] = Field(default_factory=list)

    # Metadata
    metadata: TripMetadata

    # Audit trail for user corrections
    user_corrections: List[dict] = Field(default_factory=list)

    # Helpers
    @property
    def outward_segments(self) -> List[TripSegment]:
        """All segments belonging to the outward journey, in order."""
        return [s for s in self.segments if s.journey_type == "outward"]

    @property
    def return_segments(self) -> List[TripSegment]:
        """All segments belonging to the return journey, in order."""
        return [s for s in self.segments if s.journey_type == "return"]

    @property
    def is_return_trip(self) -> bool:
        """True if the trip has at least one return segment."""
        return any(s.journey_type == "return" for s in self.segments)

    @property
    def is_multi_segment(self) -> bool:
        """True if the trip has more than one segment in total."""
        return len(self.segments) > 1

    @property
    def segment_count(self) -> int:
        return len(self.segments)

    @property
    def boarding_pass_count(self) -> int:
        return len(self.boarding_passes)
