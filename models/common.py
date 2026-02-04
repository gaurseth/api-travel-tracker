from typing import Optional, Dict
from pydantic import BaseModel, Field
from datetime import datetime


class ConfidenceFactors(BaseModel):
    ocr: float = Field(..., ge=0.0, le=1.0)
    pattern: float = Field(..., ge=0.0, le=1.0)
    context: float = Field(..., ge=0.0, le=1.0)
    airline: float = Field(..., ge=0.0, le=1.0)


class ExtractedValue(BaseModel):
    value: Optional[str] = None
    confidence: float = Field(..., ge=0.0, le=1.0)
    confidence_factors: Optional[ConfidenceFactors] = None


class Warning(BaseModel):
    field: str
    reason: str
    confidence: float = Field(..., ge=0.0, le=1.0)


class ExtractionMetadata(BaseModel):
    extraction_id: str
    engine_version: str
    method: str  # rules | ai | rules+ai
    image_quality: float = Field(..., ge=0.0, le=1.0)
    overall_confidence: float = Field(..., ge=0.0, le=1.0)
    warnings: list[Warning] = []
