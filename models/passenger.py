"""
Passenger model — represents a traveller linked to boarding passes and segments.

Firestore path: users/{userId}/passengers/{passengerId}
"""
from typing import Optional
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
