"""
Boarding Pass Attachment Model

Represents a boarding pass attached to a trip.
Stored at the trip level to avoid duplication when multiple segments reference the same boarding pass.
"""
from typing import Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class BoardingPassAttachment(BaseModel):
    """
    Represents a boarding pass attached to a trip.

    Boarding passes are stored at the trip level (not duplicated per segment).
    Multiple segments can reference the same boarding pass via boarding_pass_id.

    Use case examples:
    - Single boarding pass with multiple connecting flights
    - Adding outbound and return boarding passes separately
    - Attaching boarding pass to manually created trip
    """
    boarding_pass_id: str = Field(description="Unique identifier for this boarding pass")

    boarding_pass_data: Dict[str, Any] = Field(
        description="Complete BoardingPass object as JSON (includes all segments, passenger info, etc.)"
    )

    segment_count: int = Field(
        ge=1,
        description="Number of flight segments on this boarding pass"
    )

    attached_at: str = Field(
        description="When this boarding pass was attached (ISO-8601 datetime)"
    )

    extraction_metadata: Optional[Dict[str, Any]] = Field(
        None,
        description="Extraction quality metrics (confidence, quality_label, warnings)"
    )

    raw_ocr_text: Optional[str] = Field(
        None,
        description="Original OCR text for debugging/review"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "boarding_pass_id": "bp_abc123",
                "boarding_pass_data": {
                    "passenger": {
                        "full_name": {"value": "SMITH JOHN", "confidence": 0.95}
                    },
                    "segments": [
                        {
                            "segment_number": 1,
                            "flight": {"flight_number": {"value": "EK202", "confidence": 0.98}},
                            "route": {
                                "origin": {"iata": {"value": "DXB", "confidence": 0.99}},
                                "destination": {"iata": {"value": "JFK", "confidence": 0.99}}
                            }
                        }
                    ]
                },
                "segment_count": 1,
                "attached_at": "2026-02-10T12:34:56Z",
                "extraction_metadata": {
                    "overall_confidence": 0.87,
                    "quality": "good",
                    "warnings": []
                }
            }
        }
