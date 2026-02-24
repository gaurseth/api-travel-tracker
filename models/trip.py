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

    Multi-segment architecture:
    - segments: Array of flight legs (can be from one or multiple boarding passes)
    - boarding_passes: Boarding passes stored at trip level (no duplication)
    - Each segment references its boarding pass via boarding_pass_id

    Scenarios:
    1. Single-segment trip from boarding pass scan
    2. Multi-segment trip from single boarding pass (connecting flights)
    3. Multi-segment trip with separate boarding passes (outbound + return)
    4. Manual trip with no boarding passes
    """
    trip_id: str
    user_id: str
    tenant_id: str = Field(default="personal")

    # Trip type
    trip_type: str = Field(default="flight")  # flight | train | bus | car | hotel | other

    # Multi-segment support (PRIMARY)
    segments: List[TripSegment] = Field(
        default_factory=list,
        description="List of trip segments (flight legs)"
    )
    boarding_passes: List[BoardingPassAttachment] = Field(
        default_factory=list,
        description="Boarding passes attached to this trip (stored at trip level)"
    )

    # Legacy fields for backward compatibility (deprecated - use segments instead)
    # These are populated from first segment for single-segment trips
    origin: Optional[str] = Field(None, description="Deprecated: Use segments[0].origin")
    destination: Optional[str] = Field(None, description="Deprecated: Use segments[0].destination")
    departure_date: Optional[str] = Field(None, description="Deprecated: Use segments[0].departure_date")
    arrival_date: Optional[str] = Field(None, description="Deprecated: Use segments[0].arrival_date")
    airline_code: Optional[str] = Field(None, description="Deprecated: Use segments[0].airline_code")
    flight_number: Optional[str] = Field(None, description="Deprecated: Use segments[0].flight_number")
    passenger_name: Optional[str] = None

    # Raw data (only if from scan)
    raw_ocr_text: Optional[str] = None

    # User-added fields
    title: Optional[str] = None  # e.g., "Trip to Dubai"
    description: Optional[str] = None
    notes: Optional[str] = None
    tags: List[str] = Field(default_factory=list)

    # Metadata
    metadata: TripMetadata

    # User corrections (track changes made after initial extraction)
    user_corrections: List[dict] = Field(default_factory=list)

    # Helper properties
    @property
    def is_multi_segment(self) -> bool:
        """Check if this trip has multiple segments."""
        return len(self.segments) > 1

    @property
    def segment_count(self) -> int:
        """Total number of segments in this trip."""
        return len(self.segments)

    @property
    def boarding_pass_count(self) -> int:
        """Total number of boarding passes attached to this trip."""
        return len(self.boarding_passes)

    @property
    def has_boarding_passes(self) -> bool:
        """Check if any boarding passes are attached."""
        return len(self.boarding_passes) > 0
