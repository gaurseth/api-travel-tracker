from typing import Optional
from pydantic import BaseModel, Field
from datetime import datetime
from .boarding_pass import BoardingPass
from .common import ExtractionMetadata


class SourceInfo(BaseModel):
    upload_type: str  # camera | gallery | pdf
    client: str       # ios | android | web
    app_version: Optional[str] = None


class DocumentEnvelope(BaseModel):
    document_id: str
    document_type: str = Field(default="boarding_pass")
    tenant_id: str
    user_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    source: SourceInfo
    extraction: ExtractionMetadata
    boarding_pass: BoardingPass
