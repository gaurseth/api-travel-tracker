from typing import Optional
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
    date: Optional[ExtractedValue] = None  # ISO-8601 yyyy-mm-dd


class LocationInfo(BaseModel):
    iata: ExtractedValue
    city: Optional[ExtractedValue] = None


class RouteInfo(BaseModel):
    origin: LocationInfo
    destination: LocationInfo


class BoardingInfo(BaseModel):
    time: Optional[ExtractedValue] = None
    gate: Optional[ExtractedValue] = None
    seat: Optional[ExtractedValue] = None
    group: Optional[ExtractedValue] = None


class BarcodeInfo(BaseModel):
    present: bool
    type: Optional[str] = None
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)


class BoardingPass(BaseModel):
    airline: Optional[AirlineInfo] = None
    passenger: PassengerInfo
    flight: FlightInfo
    route: Optional[RouteInfo] = None
    boarding: Optional[BoardingInfo] = None
    pnr: Optional[ExtractedValue] = None
    sequence_number: Optional[ExtractedValue] = None
    barcode: Optional[BarcodeInfo] = None
    raw_ocr_text: Optional[str] = None
