"""
Passenger model — represents a traveller linked to boarding passes and segments.

Firestore path: users/{userId}/passengers/{passengerId}
"""
from typing import Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class Passenger(BaseModel):
    """A passenger profile belonging to a user."""
    id: str = Field(description="Unique passenger ID (e.g. 'pax_abc123')")
    name: str = Field(description="Display name (e.g. 'Gaurav Seth')")
    normalized_name: str = Field(description="Lowercase, no special chars (e.g. 'gaurav seth')")
    is_primary: bool = Field(default=False, description="True if this is the account holder")
    created_at: str = Field(description="ISO-8601 datetime")
    updated_at: str = Field(description="ISO-8601 datetime")
    deleted_at: Optional[str] = Field(None, description="ISO-8601 datetime, set on soft-delete")


class PassengerUpsertResponse(BaseModel):
    """
    Response from POST /passengers/{passenger_id}.

    - canonical=True means the server redirected this write to an existing
      passenger (same normalized_name). merged_from = the client id that was
      submitted. The client should adopt `id` as the canonical passenger id.
    - canonical=False means the client id was used as-is (created or merged
      in place).
    """
    id: str = Field(description="Canonical passenger ID the client should use")
    canonical: bool = Field(description="True if the client id was redirected to an existing passenger")
    merged_from: Optional[str] = Field(None, description="Original client id when canonical=True")
    passenger: Dict[str, Any] = Field(description="Full passenger document")
