"""
Trip model - represents a travel trip that may or may not have a boarding pass.
"""
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime
from .boarding_pass import BoardingPass
from .common import Warning


class TripMetadata(BaseModel):
    """Metadata about trip creation and modifications."""
    created_at: datetime
    updated_at: datetime
    source: str = Field(default="manual")  # manual | boarding_pass_scan | api
    extraction_metadata: Optional[dict] = None  # Only present if from boarding pass scan


class Trip(BaseModel):
    """
    A trip represents a journey that may or may not have a boarding pass attached.
    Users can create trips manually or by scanning boarding passes.
    """
    trip_id: str
    user_id: str
    tenant_id: str = Field(default="personal")

    # Trip type
    trip_type: str = Field(default="flight")  # flight | train | bus | car | hotel | other

    # Core trip details (can be filled manually or from boarding pass)
    origin: Optional[str] = None  # IATA code or city name
    destination: Optional[str] = None
    departure_date: Optional[str] = None  # ISO-8601 date
    arrival_date: Optional[str] = None

    # Flight-specific (optional)
    airline_code: Optional[str] = None
    flight_number: Optional[str] = None

    # Passenger info (optional)
    passenger_name: Optional[str] = None

    # Optional boarding pass attachment
    boarding_pass: Optional[BoardingPass] = None
    boarding_pass_attached: bool = False

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
